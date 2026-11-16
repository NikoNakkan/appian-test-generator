"""Checks a person's decision, shows what it would change, and records it.

decide(..., preview=True) applies the decision in a savepoint, rebuilds the drafts, reports
what would change and rolls back, so a reviewer sees the consequence before committing.
"""

from __future__ import annotations

from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis import drafts, review, testideas, usecases
from atg.analysis.store import open_for


def _target_ok(atlas: Atlas, kind: str, target: str) -> str:
    keys = {d["key"] for d in drafts.build(atlas)}
    door_ids = {x["id"] for d in drafts.build(atlas) for x in d["doors"]}
    if kind in {"merge", "split", "move"} and target not in door_ids:
        return f"{target!r} is not a door"
    if kind in {"rename", "approve", "reject"} and target not in keys:
        return f"{target!r} is not a draft key"
    if kind in {"exclude", "include", "shared", "not_shared"} and target not in atlas.objects:
        return f"{target!r} is not an object in this snapshot"
    if kind == "answer" and not target.isdigit():
        return "answer needs a question id"
    return ""


def _payload(atlas: Atlas, kind: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fill in what the draft looked like when the decision was made (for split and move)."""
    if kind in {"split", "move"}:
        host = next(d for d in drafts.build(atlas) if target in [x["id"] for x in d["doors"]])
        payload = {**payload, "from": [x["id"] for x in host["doors"]]}
    return payload


def _hash(atlas: Atlas, kind: str, target: str) -> str:
    if kind in {"approve", "reject"}:
        return str(drafts.card(atlas, target).get("input_hash", ""))
    if kind == "approve_use_case":
        return str((usecases.get(atlas, target) or {}).get("input_hash", ""))
    if kind == "approve_test":
        return str((testideas.get(atlas, target) or {}).get("input_hash", ""))
    return ""


def _forget(atlas: Atlas) -> None:
    for k in ("drafts", "use_cases", "test_ideas"):
        atlas.memo.pop(k, None)


def decide(
    atlas: Atlas,
    kind: str,
    target: str,
    by: str,
    reason: str = "",
    payload: dict[str, Any] | None = None,
    preview: bool = False,
) -> dict[str, Any]:
    if kind not in review.KINDS:
        return {"error": f"kind must be one of {', '.join(sorted(review.KINDS))}"}
    if not by.strip():
        return {"error": "say who decides (by)"}
    if problem := _target_ok(atlas, kind, target):
        return {"error": problem}
    if kind in {"approve_use_case", "approve_test"} and not _hash(atlas, kind, target):
        return {"error": f"{target!r} is not there to approve (is its feature approved?)"}
    full = _payload(atlas, kind, target, payload or {})
    before = {d["key"]: [x["id"] for x in d["doors"]] for d in drafts.build(atlas)}
    con = open_for(atlas)
    con.execute("SAVEPOINT decide")
    rid = review.record(atlas, kind, target, by, reason, full, _hash(atlas, kind, target))
    _forget(atlas)
    after = {d["key"]: [x["id"] for x in d["doors"]] for d in drafts.build(atlas)}
    changed = {
        "removed": sorted(set(before) - set(after)),
        "added": {k: v for k, v in after.items() if before.get(k) != v},
    }
    if preview:
        con.execute("ROLLBACK TO decide")
        con.execute("RELEASE decide")
        _forget(atlas)
        return {"preview": True, "would_change": changed}
    con.execute("RELEASE decide")
    con.commit()
    return {"recorded": rid, "changed": changed}
