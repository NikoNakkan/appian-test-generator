"""Auto-accepting a draft only on countable evidence: assessed doors, described core objects,
two challenge passes that agree, nothing open, small; and dropping back when anything changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atg.agent import atlas, tools
from atg.analysis import certainty, decide, drafts, progress, queue, usecases, verify
from tests.conftest_agent import fresh
from tests.demo import spec

CLAIMS = f"page:{spec.SITE}:claims"


@pytest.fixture
def at(tmp_path: Path) -> atlas.Atlas:
    a = fresh(tmp_path)
    queue.seed(a)
    return a


def call(at: atlas.Atlas, name: str, **args: Any) -> dict[str, Any]:
    return tools.call(at, name, args)


def draft(at: atlas.Atlas, door: str = CLAIMS) -> dict[str, Any]:
    return next(d for d in drafts.build(at) if door in [x["id"] for x in d["doors"]])


def checks(at: atlas.Atlas) -> dict[str, bool]:
    return {c["check"]: c["ok"] for c in draft(at)["certainty"]}


def note(subject: str) -> dict[str, Any]:
    obj = subject if ":" not in subject else spec.UI_LIST
    return {"subject": subject, "predicate": "note", "value": "looked at it", "level": "stated",
            "evidence": [{"object": obj}]}  # fmt: skip


def do_evidence(at: atlas.Atlas) -> None:
    d = draft(at)
    for door in d["doors"]:
        out = call(at, "submit", item=f"assess_entry:{door['id']}", status="done",
                   claims=[note(door["id"])])  # fmt: skip
        assert out["status"] == "done", out
    for u in d["core"]:
        assert call(at, "submit", item=f"describe_object:{u}", status="done", claims=[note(u)])


def challenge(at: atlas.Atlas, n: int, verdict: str) -> dict[str, Any]:
    call(at, "next_item")  # seeds challenge items for drafts ready for them
    item = certainty.challenge_ids(draft(at))[n]
    claim = {**note(CLAIMS), "predicate": "boundary_holds", "value": verdict}
    return call(at, "submit", item=item, status="done", claims=[claim])


def test_a_simple_draft_becomes_auto_accepted(at: atlas.Atlas) -> None:
    first = checks(at)
    assert first["groupings agree"] and first["small"] and first["no doubts"]
    assert not first["evidence"] and not first["runs agree"]
    assert draft(at)["status"] == "draft"
    do_evidence(at)
    assert checks(at)["evidence"] and certainty.ready_for_challenge(draft(at))
    assert challenge(at, 0, "yes")["status"] == "done"
    assert draft(at)["status"] == "draft"  # 1 of 2 runs is not enough
    challenge(at, 1, "yes")
    assert draft(at)["status"] == "auto-accepted"
    ucs = [u for u in usecases.build(at) if u["feature"] == draft(at)["key"]]
    assert ucs and ucs[0]["feature_status"] == "auto-accepted"
    m = {x["measure"]: x for x in progress.measures(at)["measures"]}
    assert (m["features approved"]["n"], m["features approved"]["auto_accepted"]) == (0, 1)
    assert m["use cases"]["of"] == 1


def test_reject_and_changes_send_it_back(at: atlas.Atlas) -> None:
    do_evidence(at)
    challenge(at, 0, "yes")
    challenge(at, 1, "yes")
    key = draft(at)["key"]
    assert decide.decide(at, "reject", key, "ana", reason="unsure")["recorded"]
    assert draft(at)["status"] == "draft"
    assert {c["check"]: c["ok"] for c in draft(at)["certainty"]}["not rejected"] is False
    decide.decide(at, "approve", key, "ana")
    assert draft(at)["status"] == "approved"  # a person's decision wins
    core = draft(at)["core"][0]
    decide.decide(at, "shared", core, "ana")  # inputs change underneath
    assert draft(at)["status"] == "stale"


def test_a_challenge_that_says_no_keeps_it_for_a_person(at: atlas.Atlas) -> None:
    do_evidence(at)
    challenge(at, 0, "yes")
    challenge(at, 1, "no")
    assert draft(at)["status"] == "draft"
    why = {c["check"]: c["why"] for c in draft(at)["certainty"]}["runs agree"]
    assert why == "A re-check said this is not one feature."
    bad = {**note(CLAIMS), "predicate": "boundary_holds", "value": "maybe"}
    assert "boundary_holds needs the value yes or no" in verify.check(at, bad)


def test_big_or_mixed_drafts_never_auto_accept(at: atlas.Atlas) -> None:
    others = [d["doors"][0]["id"] for d in drafts.build(at) if d["key"] != draft(at)["key"]]
    for door in others[:5]:
        decide.decide(at, "merge", door, "ana", payload={"with": CLAIMS})
    c = {x["check"]: x["ok"] for x in draft(at)["certainty"]}
    assert not c["small"] and not c["groupings agree"]
    assert not certainty.ready_for_challenge(draft(at))
