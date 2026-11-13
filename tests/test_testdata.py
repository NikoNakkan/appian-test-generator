"""Test data, screens and UAT scenarios on the demo export (tests/demo).

EXP_SubmitClaim paths: 1 no approval needed, 2 reviewed and not approved, 3 approved.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atg import mapdb, store
from atg.layers.pipeline import run_layers
from atg.testgen import scenarios, screens, testdata
from atg.web import tests_api
from tests.conftest import demo_export, single_root
from tests.demo import spec


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[sqlite3.Connection, int]:
    con = store.connect(Path(tmp_path_factory.mktemp("td")) / "map.db")
    sid, _ = run_layers(con, single_root(demo_export()))
    return con, sid


def test_path_data_lists_inputs_conditions_and_tasks(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    d = testdata.path_data(con, sid, spec.PM_SUBMIT, 2)
    inputs = {v["name"]: v for v in d["start_inputs"]}
    assert inputs["claim"]["kind"] == "record" and len(inputs["claim"]["fields"]) == 5
    assert inputs["amount"]["kind"] == "value"
    assert [c["needs"] for c in d["conditions"]] == [
        ["EXP_NeedsApproval(amount: amount) is true"],
        ['decision ≠ "Approve"'],
    ]
    (task,) = d["user_tasks"]
    assert task["groups"] == ["EXP_Approvers"]
    assert [d["records_written"], d["subprocesses"]] == [[], [{"name": "EXP_Notify"}]]


def test_missing_path_is_an_error(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    assert "error" in testdata.path_data(con, sid, "nope", 1)


def test_rule_data_suggests_values_to_try_and_saved_ones(
    demo: tuple[sqlite3.Connection, int],
) -> None:
    con, sid = demo
    (lines,) = testdata.rule_data(con, sid, spec.R_TOTAL)["inputs"]
    assert lines["kind"] == "record" and lines["list"]
    assert lines["try"] == ["0, 1 and several items", "empty and filled in"]
    (amount,) = testdata.rule_data(con, sid, spec.R_NEEDS)["inputs"]
    assert amount["saved"] == ["100", "900"]


def test_screens_and_how_people_reach_them(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    how = {u: [(r["how"], r["url"]) for r in rs] for u, rs in screens.routes(con, sid).items()}
    assert how == {
        spec.UI_LIST: [("site page", "/suite/sites/expenses/page/claims")],
        spec.UI_DASH: [("site page", "/suite/sites/expenses/page/dashboard")],
        spec.UI_REVIEW: [("user task", "/suite/tempo/tasks")],
        spec.UI_SUMMARY: [("record view", "/suite/tempo/records/type/claims/view/all")],
        spec.UI_CLAIM: [("start form", "/suite/tempo/records/type/claims/view/all")],
        spec.UI_UNUSED: [("not shown anywhere", "")],
    }


def test_screen_buttons_records_and_test_list(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    grid = tests_api.test_data(con, sid, spec.UI_LIST, None)
    assert grid["kind"] == "screen"
    assert {a["label"]: a["does"] for a in grid["actions"]} == {
        "New claim": ["opens the record list action “New claim” (starts EXP_SubmitClaim)"],
        "Refresh": ["starts a process from another app"],
    }
    (claims,) = grid["records_read"]
    assert (claims["table"], claims["source"], claims["sync"]["frequency"]) == (
        "exp_claim",
        "RDBMS_TABLE",
        "DAILY",
    )
    assert claims["related"] == [{"name": "EXP_ClaimLine", "kind": "ONE_TO_MANY"}]
    assert claims["computed"] == ["amountWithTax"]
    form = tests_api.test_data(con, sid, spec.UI_CLAIM, None)
    assert form["file_uploads"] == 1
    assert {f["label"]: f["kind"] for f in form["fields"]}["Line description"] == "text box"
    listing = tests_api.tests(con, sid)
    assert [len(listing["screens"]), len(listing["rules"])] == [6, 3]
    assert sum(len(p["paths"]) for p in listing["processes"]) == 5


def test_path_scenario_reads_as_steps(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    s = scenarios.path_scenario(con, sid, spec.PM_SUBMIT, 3)
    assert s["title"] == "EXP_SubmitClaim, path 3: Yes → Approved"
    assert s["steps"][0] == (
        "Open the EXP_Claim list (/suite/tempo/records/type/claims/view/all) and click “New claim”."
    )
    assert s["steps"][1] == (
        "On the start form “EXP_ClaimForm” fill in claim: “Title” (text box); "
        "amount: “Amount” (number box) and submit."
    )
    assert s["steps"][3] == (
        "Log in as a user in EXP_Approvers, open the task “Review claim” from the task list "
        "(/suite/tempo/tasks), fill in decision: “Decision” (radio buttons); "
        "comment: “Comment” (text area) and click the button “Send”."
    )
    assert s["expected"] == ["The process ends at “End”.", "New or updated rows in EXP_Claim."]
    assert not any("urn:appian" in x for k in ("preconditions", "steps") for x in s[k])


def test_screen_scenario_and_rules_have_none(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    grid = scenarios.screen_scenario(con, sid, spec.UI_LIST)
    assert grid["steps"][0] == "Open the site page “Claims” (/suite/sites/expenses/page/claims)."
    assert (
        "Use “New claim”: it opens the record list action “New claim” (starts EXP_SubmitClaim)."
        in grid["steps"]
    )
    assert "error" in tests_api.scenario(con, sid, spec.R_NEEDS, None)


def test_record_facts_for_both_record_types(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    both = testdata.records(con, sid, {spec.RT, spec.RT_LINE}, mapdb.names(con, sid))
    assert [(r["name"], r["table"]) for r in both] == [
        ("EXP_Claim", "exp_claim"),
        ("EXP_ClaimLine", "exp_claim_line"),
    ]
    assert both[1]["related"] == [{"name": "EXP_Claim", "kind": "MANY_TO_ONE"}]
