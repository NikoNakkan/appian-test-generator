"""Drafts, people's decisions, use cases, test ideas, progress and runtime authorisation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atg import cli
from atg.agent import atlas, tools
from atg.analysis import decide, drafts, labels, progress, testideas, usecases
from tests import agentdemo
from tests.conftest_agent import fresh
from tests.demo import spec

NEW, WITHDRAW = f"action:{spec.ACT_NEW}", f"action:{spec.ACT_WITHDRAW}"
PAID, REMIND = f"start:{agentdemo.PM_PAID}", f"start:{agentdemo.PM_REMIND}"


@pytest.fixture
def at(tmp_path: Path) -> atlas.Atlas:
    return fresh(tmp_path)


def call(at: atlas.Atlas, name: str, **args: Any) -> dict[str, Any]:
    return tools.call(at, name, args)


def _host(at: atlas.Atlas, door: str) -> dict[str, Any]:
    return next(d for d in drafts.build(at) if door in [x["id"] for x in d["doors"]])


def test_drafts_group_doors_and_say_why(at: atlas.Atlas) -> None:
    new = _host(at, NEW)
    assert [x["name"] for x in new["doors"]] == ["New claim", "Review claim"]
    assert any("runs in a process" in w for w in new["why"])
    assert _host(at, PAID)["key"] != new["key"]
    marks = labels.labels(at)
    assert marks[spec.UI_UNUSED][0] == "unreached"
    assert marks[spec.RT][0] == "supporting"
    assert marks[spec.UI_CLAIM] == ("core", f"draft {new['key']}")
    assert all(
        lab in {"core", "shared", "supporting", "unreached", "container", "excluded"}
        for lab, _ in marks.values()
    )


def test_merge_split_preview_rename_exclude(at: atlas.Atlas) -> None:
    preview = decide.decide(at, "merge", PAID, "ana", payload={"with": NEW}, preview=True)
    assert preview["preview"] and preview["would_change"]["removed"]
    assert _host(at, PAID)["key"] != _host(at, NEW)["key"]  # nothing kept
    assert decide.decide(at, "merge", PAID, "ana", payload={"with": NEW})["recorded"]
    assert _host(at, PAID)["key"] == _host(at, NEW)["key"]
    assert "a person put these together" in _host(at, NEW)["why"]
    decide.decide(at, "split", PAID, "ana", reason="different goal")
    assert _host(at, PAID)["key"] != _host(at, NEW)["key"]
    key = _host(at, NEW)["key"]
    decide.decide(at, "rename", key, "ana", payload={"name": "Claim an expense"})
    assert _host(at, NEW)["name"] == "Claim an expense"
    decide.decide(at, "exclude", spec.UI_UNUSED, "ana", reason="old")
    assert labels.labels(at)[spec.UI_UNUSED] == ("excluded", "old")
    assert decide.decide(at, "merge", "nope", "ana")["error"]
    assert decide.decide(at, "approve", key, "")["error"]


def test_approval_use_cases_tests_and_staleness(at: atlas.Atlas) -> None:
    key = _host(at, NEW)["key"]
    assert usecases.build(at) == []  # nothing before approval
    decide.decide(at, "approve", key, "ana")
    assert _host(at, NEW)["status"] == "approved"
    ucs = {u["id"]: u for u in usecases.build(at)}
    assert set(ucs) == {f"uc:{NEW}", f"uc:task:{spec.PM_SUBMIT}:2"}  # starter + hand-off
    uc = ucs[f"uc:{NEW}"]
    assert uc["actor"] == "EXP_Employees" and uc["goal_from"] == "from the door title"
    assert "someone outside EXP_Employees is refused" in uc["negatives"]
    assert len(uc["alternatives"]) == 2
    decide.decide(at, "approve_use_case", uc["id"], "ana")
    ideas = testideas.build(at)
    assert {i["technique"] for i in ideas} == {"scenario", "access"}
    assert all(
        "needs a person" in " ".join(i["basis"]) for i in ideas if i["technique"] == "scenario"
    )
    decide.decide(at, "approve_test", ideas[0]["id"], "ana")
    m = {x["measure"]: x for x in progress.measures(at)["measures"]}
    assert (m["features approved"]["n"], m["use cases"]["n"]) == (1, 1)
    assert m["test design"]["by_technique"]["scenario"]["n"] == 1
    decide.decide(at, "not_shared", spec.R_NEEDS, "ana")  # changes the draft's inputs
    decide.decide(at, "merge", REMIND, "ana", payload={"with": NEW})
    assert _host(at, NEW)["status"] == "stale"
    m = {x["measure"]: x for x in progress.measures(at)["measures"]}
    assert (m["features approved"]["n"], m["features approved"]["stale"]) == (0, 1)


def test_progress_counts_without_a_blended_percentage(at: atlas.Atlas) -> None:
    out = call(at, "progress")
    names = [m["measure"] for m in out["measures"]]
    assert len(names) == 11 and "percent" not in str(out)
    m = {x["measure"]: x for x in out["measures"]}
    assert m["doors listed"]["n"] == m["doors listed"]["of"] == 10
    assert m["doors assessed"]["n"] == 0 and m["feature drafts"]["of"] is None
    assert out["health"]["open_questions"] == 0


def test_runtime_needs_authorisation(at: atlas.Atlas) -> None:
    from atg.analysis import authorise

    refused = call(at, "record", user="u1", id=NEW, result="seen", environment="test-env")
    assert "authorisation" in refused["error"]
    assert authorise.grant(at, "test-env", "", "observe", "ana")["granted"]["mode"] == "observe"
    ok = call(at, "record", user="u1", id=NEW, result="matches", environment="test-env", claim="7")
    assert ok["recorded"]
    decide.decide(at, "select_runtime", "7", "ana")
    m = {x["measure"]: x for x in progress.measures(at)["measures"]}
    assert (m["runtime checks"]["n"], m["runtime checks"]["of"]) == (1, 1)


def test_cli_review_and_authorise(at: atlas.Atlas, capsys: pytest.CaptureFixture[str]) -> None:
    db = Path(at.con.execute("PRAGMA database_list").fetchone()[2])
    key = _host(at, NEW)["key"]
    assert cli.main(["review", "approve", key, "--by", "ana", "--preview", "--db", str(db)]) == 0
    assert '"preview": true' in capsys.readouterr().out
    assert (
        cli.main(["authorise", "--env", "e", "--mode", "act", "--by", "ana", "--db", str(db)]) == 0
    )
    assert cli.main(["review", "approve", "nope", "--by", "ana", "--db", str(db)]) == 1
