"""The agent tools on the demo plus gates, role maps, a timer and a message process
(tests/agentdemo.py)."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from atg import store
from atg.agent import atlas, doors, mcp, tools
from atg.layers.pipeline import run_layers
from tests import agentdemo
from tests.conftest import single_root
from tests.demo import spec


@pytest.fixture(scope="module")
def at(tmp_path_factory: pytest.TempPathFactory) -> atlas.Atlas:
    folder = agentdemo.build(tmp_path_factory.mktemp("agent"))
    con = store.connect(folder.parent / "map.db")
    sid, results = run_layers(con, single_root(folder))
    assert all(r.ok for r in results), [r.name for r in results if not r.ok]
    return atlas.load(con, sid)


def call(at: atlas.Atlas, name: str, **args: Any) -> dict[str, Any]:
    out = tools.call(at, name, args)
    json.dumps(out)  # every answer must be plain JSON
    return out


def test_overview_lists_every_door(at: atlas.Atlas) -> None:
    o = call(at, "overview")
    assert o["app"] == ["Expense Claims"]
    assert o["doors"] == {
        "record list action": 1,
        "related action": 1,
        "record view": 1,
        "site page": 3,
        "web API": 1,
        "user task": 1,
        "timer start": 1,
        "message start": 1,
    }
    assert o["doors_with_a_gate"] == 3  # dashboard, withdraw, the review task


def test_gates_resolve_constants_and_own_data(at: atlas.Atlas) -> None:
    dash = call(at, "find", query="/suite/sites/expenses/page/dashboard")["results"]
    assert [d["name"] for d in dash] == ["Dashboard"]
    gates = call(at, "who", id=dash[0]["id"])["gates"]
    assert gates == [
        {
            "kind": "group",
            "groups": ["EXP_Approvers"],
            "says": "only members of EXP_Approvers",
            "confidence": "resolved",
            "where": "whole",
            "guard": "visibility",
        }
    ]
    withdraw = call(at, "who", id=f"action:{spec.ACT_WITHDRAW}")["gates"]
    assert [(g["groups"], g["confidence"]) for g in withdraw] == [(["EXP_Employees"], "read")]
    lst = call(at, "card", id=spec.UI_LIST)
    assert [g["kind"] for g in lst["gates"]] == ["own data"]
    assert lst["gates"][0]["where"] == "part"


def test_visible_to_a_group(at: atlas.Atlas) -> None:
    v = call(at, "visible_to", group="exp_approvers")
    assert {d["name"] for d in v["doors_for_this_group"]} == {"Dashboard", "Review claim"}
    assert "Withdraw" not in {d["name"] for d in v["doors_with_no_gate"]}
    assert call(at, "visible_to", group="nobody")["error"]


def test_screen_card_links_both_ways(at: atlas.Atlas) -> None:
    c = call(at, "card", id=spec.UI_CLAIM)
    assert c["name"] == "EXP_ClaimForm"
    assert spec.UI_LINES in {u["id"] for u in c["uses"]}
    assert {d["name"] for d in c["reached_from"]} == {"New claim"}
    assert any("Submit claim" in x and "submits the form" in x for x in c["changes"])
    assert "amount (Decimal)" in c["needs"]
    found = call(at, "find", query="New expense claim")["results"]
    assert found[0]["id"] == spec.UI_CLAIM and found[0]["matched_by"] == "text on the screen"


def test_process_paths_cover_every_option_once(at: atlas.Atlas) -> None:
    p = call(at, "process", id=spec.PM_SUBMIT)
    assert p["options"] == 4 and len(p["paths"]) == 3 and not p["not_reachable"]
    assert p["tasks"] == [{"task": "Review claim", "for": ["EXP_Approvers"]}]
    changes = {c for path in p["paths"] for c in path["changes"]}
    assert {
        'sets status to "Approved"',
        "calls integration EXP_PayClaim",
        "starts process EXP_Notify",
        "gives a task to EXP_Approvers",
    } <= changes
    assert call(at, "process", id=spec.UI_LIST)["error"]


def test_record_and_coverage(at: atlas.Atlas) -> None:
    assert call(at, "record", user="employee1", id="x", result="nope")["error"]
    call(at, "record", user="employee1", id=f"action:{spec.ACT_NEW}", result="matches")
    call(
        at,
        "record",
        user="employee1",
        id=f"action:{spec.ACT_WITHDRAW}",
        result="differs",
        note="shown although gated",
    )
    cov = call(at, "coverage", user="employee1")
    assert (cov["doors"], cov["doors_seen"]) == (10, 2)
    assert [d["id"] for d in cov["differs_or_broken"]] == [f"action:{spec.ACT_WITHDRAW}"]
    assert call(at, "coverage", user="someone else")["doors_seen"] == 0


def test_missing_arguments_and_unknown_ids(at: atlas.Atlas) -> None:
    assert "needs: query" in call(at, "find")["error"]
    assert "no tool" in call(at, "nope")["error"]
    assert "not in this export" in call(at, "card", id=spec.OUTSIDE_RULE)["error"]


def test_mcp_over_stdio(at: atlas.Atlas) -> None:
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "find", "arguments": {"query": "Claims"}},
        },
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "card"}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"},
    ]
    out = io.StringIO()
    mcp.serve(at.con, at.sid, io.StringIO("\n".join(json.dumps(m) for m in msgs)), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5]
    assert replies[0]["result"]["capabilities"] == {"tools": {}}
    assert {t["name"] for t in replies[1]["result"]["tools"]} == set(tools.BY_NAME)
    hits = json.loads(replies[2]["result"]["content"][0]["text"])["results"]
    assert hits[0]["name"] == "Claims" and not replies[2]["result"]["isError"]
    assert replies[3]["result"]["isError"]
    assert replies[4]["error"]["code"] == -32601


def test_findings_survive_reconnect(at: atlas.Atlas) -> None:
    db = Path(at.con.execute("PRAGMA database_list").fetchone()[2])
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM findings").fetchone()[0] >= 2


def test_door_titles_written_as_sail_read_as_text() -> None:
    assert doors.readable('#"SYSTEM_SYSRULES_rtd_getDefaultSummaryViewName"()', "view 1") == (
        "Summary"
    )
    assert doors.readable('="Πληρωμές"', "view 2") == "Πληρωμές"
    assert doors.readable('rule!T("x", "Detalle")', "view 3") == "x"
    assert doors.readable('#"_a-0000"()', "view 4") == "view 4"
    assert doors.readable("History", "view 5") == "History"
