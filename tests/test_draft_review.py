"""One reviewer per draft: the brief holds what it needs, next_item(draft=...) hands out only
that draft's work and ends with the review, the review is checked, and its title names the
draft until a person renames it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atg.agent import atlas, tools
from atg.analysis import decide, drafts, reviews
from tests.conftest_agent import fresh
from tests.demo import spec

CLAIMS = f"page:{spec.SITE}:claims"


@pytest.fixture
def at(tmp_path: Path) -> atlas.Atlas:
    return fresh(tmp_path)


def call(at: atlas.Atlas, name: str, **args: Any) -> dict[str, Any]:
    return tools.call(at, name, args)


def draft(at: atlas.Atlas) -> dict[str, Any]:
    return next(d for d in drafts.build(at) if CLAIMS in [x["id"] for x in d["doors"]])


def claim(pred: str, value: str, subject: str = CLAIMS) -> dict[str, Any]:
    return {"subject": subject, "predicate": pred, "value": value, "level": "inferred",
            "evidence": [{"object": spec.UI_LIST}]}  # fmt: skip


def work_until_review(at: atlas.Atlas, key: str) -> dict[str, Any]:
    d = draft(at)
    mine = {x["id"] for x in d["doors"]} | set(d["core"]) | {reviews.item_id(d)}
    for _ in range(100):
        item = call(at, "next_item", draft=key)
        assert item["subject"] in mine or item["item"] in mine, item
        if item["kind"] == "review_draft":
            return item
        out = call(at, "submit", item=item["item"], status="done")
        assert out["status"] == "done", out
    raise AssertionError("never reached the review")


def test_brief_has_what_a_reviewer_needs(at: atlas.Atlas) -> None:
    b = call(at, "brief", key=CLAIMS)
    assert b["draft"]["key"] == draft(at)["key"]
    parts = {"doors", "screens", "processes", "records", "rules_and_other", "related_drafts"}
    assert parts <= set(b)
    assert b["doors"][0]["url"] and b["screens"]
    assert any(s["fields"] or s["buttons"] or s["texts"] for s in b["screens"])
    assert b["unfinished"]["items"], "nothing is assessed yet"
    assert all({"prefix", "count", "types"} <= set(n) for n in b["naming"])
    assert "brief" in call(at, "playbook", role="reviewer")["instructions"]


def test_a_review_names_the_draft_and_suggests(at: atlas.Atlas) -> None:
    key = draft(at)["key"]
    item = work_until_review(at, key)
    assert item["brief"]["draft"]["key"] == key and "D1" in item["questions"]
    other = next(d["key"] for d in drafts.build(at) if d["key"] != key)
    long = claim("feature_title", "one two three four five six seven eight nine")
    bad = call(at, "submit", item=item["item"], status="done", claims=[long])
    assert "refused" in bad["error"]
    assert any("at most 8 words" in p for p in bad["problems"])
    assert any("exactly one feature_title" in p for p in bad["problems"])
    outside = claim("feature_summary", "x", subject=spec.UI_LIST)
    if spec.UI_LIST not in draft(at)["core"]:
        bad2 = call(at, "submit", item=item["item"], status="done",
                    claims=[claim("feature_title", "Ver reclamaciones"), outside])  # fmt: skip
        assert any("door or core object" in p for p in bad2["problems"])
    good = [
        claim("feature_title", "Ver reclamaciones"),
        claim("feature_summary", "An employee looks through their expense claims."),
        claim("same_feature_as", f"{other}: both list the same claims"),
    ]
    assert call(at, "submit", item=item["item"], status="done", claims=good)["status"] == "done"
    d = draft(at)
    assert d["name"] == "Ver reclamaciones" and d["reviewed"]
    assert d["summary"].startswith("An employee")
    assert d["suggest"][0]["target"] == other
    assert call(at, "next_item", draft=key)["done"]
    decide.decide(at, "rename", key, "ana", payload={"name": "Claims list"})
    assert draft(at)["name"] == "Claims list"  # a person's name wins
