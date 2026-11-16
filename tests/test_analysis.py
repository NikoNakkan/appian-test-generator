"""The work queue and the ledger: what comes next, what is refused, what survives a restart,
and the reader's new facts (role maps, timer and message starts, lifecycle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atg.agent import atlas, tools
from atg.analysis import drafts
from atg.analysis.store import open_for
from tests import agentdemo
from tests.conftest_agent import fresh, reimport
from tests.demo import spec


@pytest.fixture
def at(tmp_path: Path) -> atlas.Atlas:
    return fresh(tmp_path)


def call(at: atlas.Atlas, name: str, **args: Any) -> dict[str, Any]:
    return tools.call(at, name, args)


def test_role_maps_triggers_and_access_check(at: atlas.Atlas) -> None:
    new = call(at, "card", id=f"action:{spec.ACT_NEW}")
    assert new["permission"]["groups"] == ["EXP_Employees"]
    starts = {
        d["name"]: d["trigger"] for d in call(at, "doors")["doors"] if d["id"].startswith("start:")
    }
    assert starts == {"EXP_Reminder": "timer", "EXP_MarkPaid": "message"}
    issues = call(at, "access_check")["mismatches"]
    assert [i["name"] for i in issues] == ["New claim", "Withdraw"]
    assert "EXP_Employees who may not use it" in issues[1]["issue"]
    kinds = {a["actor"]: a["kind"] for a in call(at, "actors")["actors"]}
    assert kinds["EXP_Approvers"] == "group"
    assert kinds["the system, on a timer (runs as the process designer)"] == "system"
    assert kinds["the record's own user (owner or creator)"] == "relationship"
    assert "never_in_an_export" in call(at, "census")


def test_lifecycle_finds_statuses_and_gaps(at: atlas.Atlas) -> None:
    rows = {r["record_type"]: r for r in call(at, "lifecycle")["record_types"]}
    claim = rows["EXP_Claim"]
    assert sorted(claim["statuses_set"]["status"]) == ["Approved", "Paid", "Withdrawn"]
    assert "nothing deletes it (kept forever, or deleted elsewhere?)" in claim["gaps"]
    assert any("writes it" in g for g in rows["EXP_ClaimLine"]["gaps"])


def _good_claim(door: str) -> dict[str, Any]:
    return {
        "subject": door,
        "predicate": "starts",
        "value": "EXP_SubmitClaim",
        "level": "stated",
        "evidence": [
            {"object": spec.PM_SUBMIT, "quote": "Needs approval?"},
            {"object": spec.PM_SUBMIT, "path": [spec.PM_SUBMIT, spec.UI_REVIEW]},
        ],
    }


def test_next_item_submit_and_refusals(at: atlas.Atlas) -> None:
    first = call(at, "next_item")
    assert first["kind"] == "assess_entry" and set(first["questions"]) == {
        f"Q{i}" for i in range(1, 7)
    }
    item = first["item"]
    bad = dict(
        _good_claim(first["subject"]),
        level="human-confirmed",
        evidence=[{"object": spec.PM_SUBMIT, "quote": "not in the source"}],
    )
    refused = call(at, "submit", item=item, status="done", claims=[bad])
    assert refused["error"] and len(refused["problems"]) == 2
    cut = [{"object": spec.PM_SUBMIT, "truncated": True, "total": 120}]
    assert "cut short" in call(at, "submit", item=item, status="done", reads=cut)["problems"][0]
    ok = call(
        at,
        "submit",
        item=item,
        status="done-partial",
        reads=cut,
        claims=[_good_claim(first["subject"])],
    )
    assert ok == {"item": item, "status": "done-partial", "claims": 1, "reads": 1}
    again = call(at, "submit", item=item, status="done", claims=[_good_claim(first["subject"])])
    assert "nothing changed" in again["says"]
    assert open_for(at).execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
    assert call(at, "next_item")["item"] != item


def test_questions_unblock_and_leases_expire(at: atlas.Atlas) -> None:
    from atg.analysis import decide

    first = call(at, "next_item")
    assert "question" in call(at, "submit", item=first["item"], status="needs-human")["problems"][0]
    call(at, "submit", item=first["item"], status="needs-human", question="Is this used?")
    state = call(at, "resume")
    assert [q["text"] for q in state["open_questions"]] == ["Is this used?"]
    qid = str(state["open_questions"][0]["id"])
    assert decide.decide(at, "answer", qid, "reviewer", payload={"text": "yes"})["recorded"]
    call(at, "resume")
    assert call(at, "next_item")["item"] == first["item"]  # unblocked items go first
    con = open_for(at)
    con.execute("UPDATE items SET lease_until = '2000-01-01' WHERE status = 'leased'")
    con.commit()
    assert call(at, "resume")["items"].get("leased", 0) == 0


def test_finished_work_is_reused_on_reimport(at: atlas.Atlas) -> None:
    first = call(at, "next_item")
    call(at, "submit", item=first["item"], status="done", claims=[_good_claim(first["subject"])])
    second = reimport(at)
    call(second, "resume")
    row = (
        open_for(second)
        .execute(
            "SELECT status, note FROM items WHERE snapshot_id = ? AND id = ?",
            (second.sid, first["item"]),
        )
        .fetchone()
    )
    assert row == ("done", "reused from snapshot 1")
    assert (
        open_for(second)
        .execute("SELECT COUNT(*) FROM claims WHERE snapshot_id = ?", (second.sid,))
        .fetchone()[0]
        == 1
    )


def test_injected_text_is_only_data(at: atlas.Atlas) -> None:
    first = call(at, "next_item")
    sneaky = dict(_good_claim(first["subject"]), predicate="approve")
    out = call(at, "submit", item=first["item"], status="done", claims=[sneaky])
    assert "predicate must be one of" in out["problems"][0]
    names = set(tools.BY_NAME)
    assert not names & {"review", "approve", "decide", "authorise"}  # people only
    assert agentdemo.PM_REMIND in at.objects


def test_draft_names_are_unique() -> None:
    by_id = {
        "a": {"in": "Claims site", "kind": "page"},
        "b": {"in": "Payments site", "kind": "page"},
        "c": {"in": "Claims site", "kind": "page"},
        "d": {"in": "", "kind": "page"},
    }
    out: list[dict[str, Any]] = [
        {"key": k, "name": "Create", "doors": [{"id": k, "kind": "page"}]} for k in "abcd"
    ]
    out.append({"key": "e", "name": "Create", "doors": [{"id": "a", "kind": "page"}]})
    drafts.unique_names(out, by_id, {"e": "Create"})
    names = [d["name"] for d in out]
    assert names[4] == "Create"  # a person's name is kept
    assert len(set(names[:4])) == 4
    assert names[1] == "Create · Payments site"
