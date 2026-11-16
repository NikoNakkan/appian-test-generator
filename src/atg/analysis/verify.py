"""Checks an agent claim against the map before it is stored. A claim that fails is refused,
with the reason, so the agent can correct it; nothing unverified enters the ledger.

A claim: {"subject": id, "predicate": one of PREDICATES, "value": text, "level": one of
AGENT_LEVELS, "evidence": [{"object": id, "quote"?: text, "path"?: [id, id, ...]}]}
  - every id (subject, evidence object, path step) must exist in this snapshot;
  - a quote must appear in that object's stored source (SAIL, settings or node details);
  - a path must follow real links, each step using or used by the next;
  - the agent may only claim "stated", "inferred" or "statically supported": human-confirmed
    and runtime-observed come from people and runtime checks, never from the agent.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas

PREDICATES = frozenset(
    {
        "starts",
        "writes",
        "deletes",
        "reads",
        "sets_status",
        "assigns_task_to",
        "guarded_by",
        "shown_only_to",
        "same_as",
        "leaves_app",
        "purpose",
        "part_of",
        "actor_goal",
        "unreached_because",
        "gap_reason",
        "lifecycle_note",
        "note",
        "boundary_holds",
    }
)
AGENT_LEVELS = frozenset({"stated", "inferred", "statically supported"})
ALL_LEVELS = (*sorted(AGENT_LEVELS), "human-confirmed", "runtime-observed")
_SPACE = re.compile(r"\s+")


def exists(atlas: Atlas, key: str) -> bool:
    return key in atlas.objects or doors.by_id(atlas, key) is not None


def source(atlas: Atlas, key: str) -> str:
    """Everything stored for an object or door, as one searchable text."""
    door = doors.by_id(atlas, key)
    if door is not None:
        return json.dumps(door, ensure_ascii=False)
    parts = [atlas.text(key), json.dumps(atlas.det(key), ensure_ascii=False)]
    parts += [
        d
        for (d,) in atlas.con.execute(
            "SELECT details FROM node_details WHERE snapshot_id = ? AND pm_uuid = ?",
            (atlas.sid, key),
        )
    ]
    parts += [
        lab or ""
        for (lab,) in atlas.con.execute(
            "SELECT label FROM nodes WHERE snapshot_id = ? AND pm_uuid = ?", (atlas.sid, key)
        )
    ]
    parts += [
        c or ""
        for (c,) in atlas.con.execute(
            "SELECT condition FROM flows WHERE snapshot_id = ? AND pm_uuid = ?", (atlas.sid, key)
        )
    ]
    return "\n".join(parts)


def _norm(s: str) -> str:
    return _SPACE.sub(" ", s.replace('\\"', '"')).strip()


def _linked(atlas: Atlas, a: str, b: str) -> bool:
    return b in atlas.uses.get(a, []) or a in atlas.uses.get(b, [])


def check(atlas: Atlas, claim: Any) -> list[str]:
    if not isinstance(claim, dict):
        return ["a claim must be an object"]
    problems = []
    subject, pred, level = claim.get("subject", ""), claim.get("predicate"), claim.get("level")
    if not exists(atlas, str(subject)):
        problems.append(f"subject {subject!r} is not in this snapshot")
    if pred not in PREDICATES:
        problems.append(f"predicate must be one of {', '.join(sorted(PREDICATES))}")
    if level not in AGENT_LEVELS:
        problems.append(f"level must be one of {', '.join(sorted(AGENT_LEVELS))}")
    if not str(claim.get("value", "")).strip() or len(str(claim.get("value"))) > 500:
        problems.append("value must be 1 to 500 characters")
    if pred == "boundary_holds" and str(claim.get("value", "")).strip().lower() not in {
        "yes",
        "no",
    }:
        problems.append("boundary_holds needs the value yes or no")
    evidence = claim.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return [*problems, "evidence must list at least one object"]
    for ev in evidence:
        obj = str(ev.get("object", "")) if isinstance(ev, dict) else ""
        if not exists(atlas, obj):
            problems.append(f"evidence object {obj!r} is not in this snapshot")
            continue
        quote = ev.get("quote")
        if quote and _norm(str(quote)) not in _norm(source(atlas, obj)):
            problems.append(f"quote not found in {atlas.name(obj) or obj}: {str(quote)[:60]!r}")
        path = ev.get("path") or []
        bad = [(a, b) for a, b in itertools.pairwise(path) if not _linked(atlas, a, b)]
        if bad:
            problems.append(f"path step {bad[0][0]} -> {bad[0][1]} is not a link in the map")
    return problems
