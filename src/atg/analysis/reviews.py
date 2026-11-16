"""The agent's review of a feature draft: a plain title, what a user does there, who does it,
and suggestions (same feature as another draft, split some doors out). One review item per
draft and per version of its inputs, so a merge or a new import asks for a fresh review.

The title replaces the made-up name only until a person renames the draft. Suggestions are
shown to people; only a person merges or splits.
"""

from __future__ import annotations

from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis.store import open_for

PREVIEW = 8
TITLE, SUMMARY, ACTOR = "feature_title", "feature_summary", "feature_actor"
SAME, RELATED, SPLIT = "same_feature_as", "related_feature", "split_suggested"
PREDICATES = frozenset({TITLE, SUMMARY, ACTOR, SAME, RELATED, SPLIT})
MAX_TITLE_WORDS = 8
QUESTIONS = {
    "D1": "What does a user do here, in the words a user would use? (feature_title, at most "
    f"{MAX_TITLE_WORDS} words, in the app's language; feature_summary, one or two sentences)",
    "D2": "Who does it: which kind of user, or a timer or another system? (feature_actor)",
    "D3": "Is another draft the same business feature? (same_feature_as: the other draft's key)",
    "D4": "How does it relate to the other drafts listed: before, after, uses its data? "
    "(related_feature: '<key>: how')",
    "D5": "Does any door here belong to a different feature? (split_suggested, about that door)",
    "answer": "submit(item, 'done', claims) with exactly one feature_title and one "
    "feature_summary; every claim's subject is a door or core object of this draft, with "
    "evidence quoting the labels, names or texts you based it on",
}


def item_id(d: dict[str, Any]) -> str:
    return f"review:{d['key']}:{d['input_hash'][:PREVIEW]}"


def target(value: str, keys: set[str]) -> str:
    """The draft key a suggestion starts with (keys contain colons: page:<site>:<page>)."""
    found = [k for k in keys if value == k or value.startswith((k + ":", k + " "))]
    return max(found, key=len, default="")


def check(draft: dict[str, Any], others: set[str], claims: list[Any], done: bool) -> list[str]:
    """Rules a review must meet on top of verify.check (which proves ids and quotes)."""
    mine = {x["id"] for x in draft["doors"]} | set(draft["core"])
    problems = []
    for i, c in enumerate(claims, 1):
        if not isinstance(c, dict):
            continue
        pred, value = c.get("predicate"), str(c.get("value", "")).strip()
        if c.get("subject") not in mine:
            problems.append(f"claim {i}: the subject must be a door or core object of this draft")
        if pred == TITLE and (len(value.split()) > MAX_TITLE_WORDS or len(value) > 80):
            problems.append(f"claim {i}: a title has at most {MAX_TITLE_WORDS} words")
        if pred == SUMMARY and len(value) > 400:
            problems.append(f"claim {i}: a summary is at most 400 characters")
        if pred in {SAME, RELATED} and not target(value, others):
            problems.append(f"claim {i}: {pred} must start with another draft's key")
    count = [c.get("predicate") for c in claims if isinstance(c, dict)]
    if done and (count.count(TITLE) != 1 or count.count(SUMMARY) != 1):
        problems.append("a finished review has exactly one feature_title and one feature_summary")
    return problems


def apply(atlas: Atlas, out: list[dict[str, Any]], given: dict[str, str]) -> None:
    """Put each draft's latest finished review on it; its title becomes the name unless a
    person named the draft."""
    con = open_for(atlas)
    done = {
        i
        for (i,) in con.execute(
            "SELECT id FROM items WHERE snapshot_id = ? AND kind = 'review_draft' "
            "AND status IN ('done', 'done-partial')",
            (atlas.sid,),
        )
    }
    said: dict[str, list[tuple[str, str]]] = {}
    for item, pred, value in con.execute(
        "SELECT item_id, predicate, value FROM claims WHERE snapshot_id = ? AND item_id LIKE "
        "'review:%' ORDER BY id",
        (atlas.sid,),
    ):
        said.setdefault(item, []).append((pred, value))
    keys = {d["key"] for d in out}
    for d in out:
        d["rule_name"] = d["name"]
        rid = item_id(d)
        claims = said.get(rid, []) if rid in done else []
        first = {p: v for p, v in reversed(claims)}
        d["reviewed"] = bool(claims)
        d["summary"] = first.get(SUMMARY, "")
        d["actor_says"] = first.get(ACTOR, "")
        d["suggest"] = [
            {"kind": p, "target": target(v, keys) if p != SPLIT else "", "says": v}
            for p, v in claims
            if p in {SAME, RELATED, SPLIT}
        ]
        if first.get(TITLE) and d["key"] not in given:
            d["name"] = first[TITLE]
