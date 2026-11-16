"""People's decisions, kept as an append-only list and replayed on every build.

Kinds (target in brackets):
  merge [door] {"with": door}           these doors belong together (must-link)
  split [door] {"doors": [...], "from": [...]}   these doors leave their draft (cannot-link)
  move [door] {"to": door, "from": [...]}        this door joins the draft of another door
  rename [draft key] {"name": text}
  exclude [object] / include [object]   leave an object out of the accounting (or bring it back)
  shared [object] / not_shared [object] override the shared threshold
  approve [draft key]                   approve the boundary as it is now (input hash kept)
  reject [draft key]                    do not auto-accept it: a person must look
  approve_use_case [use case id], approve_test [test id]
  answer [question id] {"text": ...}    answers the agent's question and unblocks its item
  select_runtime [claim id]             pick a claim to be checked in a running environment
An approval keeps the input hash it was given on; when the inputs change (a re-import, a
split) the approval shows as stale, never silently carried over. The agent has no tool that
reaches this module: only people decide (atg review, or the web tool).
"""

from __future__ import annotations

import json
from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis.store import now, open_for

KINDS = frozenset(
    {
        "merge",
        "split",
        "move",
        "rename",
        "exclude",
        "include",
        "shared",
        "not_shared",
        "approve",
        "reject",
        "approve_use_case",
        "approve_test",
        "answer",
        "select_runtime",
    }
)


def _rows(atlas: Atlas) -> list[tuple[str, str, dict[str, Any], str, str]]:
    con = open_for(atlas)
    return [
        (k, t, json.loads(p or "{}"), h or "", r or "")
        for k, t, p, h, r in con.execute(
            "SELECT kind, target, payload, input_hash, reason FROM decisions ORDER BY id"
        )
    ]


def constraints(atlas: Atlas) -> dict[str, Any]:
    must: list[tuple[str, str]] = []
    cannot: set[frozenset[str]] = set()
    names: dict[str, str] = {}
    excluded: dict[str, str] = {}
    shared: dict[str, bool] = {}
    for kind, target, p, _, reason in _rows(atlas):
        if kind == "merge":
            must.append((target, str(p.get("with", ""))))
            cannot.discard(frozenset((target, str(p.get("with", "")))))
        elif kind in {"split", "move"}:
            leaving = p.get("doors") or [target]
            for x in leaving:
                cannot |= {frozenset((x, y)) for y in p.get("from", []) if y not in leaving}
            must = [(a, b) for a, b in must if frozenset((a, b)) not in cannot]
            if kind == "move":
                must.append((target, str(p.get("to", ""))))
        elif kind == "rename":
            names[target] = str(p.get("name", ""))
        elif kind == "exclude":
            excluded[target] = reason or "excluded by a person"
        elif kind == "include":
            excluded.pop(target, None)
        elif kind in {"shared", "not_shared"}:
            shared[target] = kind == "shared"
    return {"must": must, "cannot": cannot, "names": names, "excluded": excluded, "shared": shared}


def status(atlas: Atlas, kind: str, target: str, input_hash: str) -> str:
    hashes = [h for k, t, _, h, _ in _rows(atlas) if k == kind and t == target]
    if not hashes:
        return "draft"
    return "approved" if hashes[-1] == input_hash else "stale"


def record(
    atlas: Atlas,
    kind: str,
    target: str,
    by: str,
    reason: str = "",
    payload: dict[str, Any] | None = None,
    input_hash: str = "",
) -> int:
    con = open_for(atlas)
    cur = con.execute(
        "INSERT INTO decisions (snapshot_id, kind, target, payload, by, reason, input_hash, at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (atlas.sid, kind, target, json.dumps(payload or {}), by, reason, input_hash, now()),
    )
    if kind == "answer":
        con.execute(
            "UPDATE questions SET status = 'answered', answer = ?, answered_by = ?, "
            "answered_at = ? WHERE id = ?",
            (str((payload or {}).get("text", "")), by, now(), int(target)),
        )
    return int(cur.lastrowid or 0)
