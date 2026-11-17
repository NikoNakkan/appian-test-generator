"""Layer 2 and 3 views: decision points of an object, test paths of a process, test users."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from atg import mapdb, pathdb
from atg.sail.explain import phrase


def _names(con: sqlite3.Connection, sid: int) -> dict[str, tuple[str, str]]:
    return {
        u: (t, n)
        for u, t, n in con.execute(
            "SELECT uuid, type, name FROM objects WHERE snapshot_id = ?", (sid,)
        )
    }


def paths(con: sqlite3.Connection, sid: int, pm: str, no: int | None = None) -> dict[str, Any]:
    """The test paths of a process, or only path `no` (a process can have 20,000)."""
    labels = {
        g: lab or tn
        for g, lab, tn in con.execute(
            "SELECT gui_id, label, type_name FROM nodes WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    }
    n = mapdb.names(con, sid)
    objects = _names(con, sid)
    stats = con.execute(
        "SELECT feasible, infeasible, truncated, loops FROM path_stats "
        "WHERE snapshot_id = ? AND pm_uuid = ?",
        (sid, pm),
    ).fetchone()
    out = []
    if no is None:
        found = pathdb.read(con, sid, pm)
    else:
        found = [p for p in [pathdb.read_one(con, sid, pm, no)] if p is not None]
    for p in found:
        out.append(
            {
                "no": p.no,
                "steps": p.steps,
                "loops": p.loops,
                "decisions": [
                    {
                        **d,
                        "gateway_label": labels.get(d["gateway"], ""),
                        "to_label": labels.get(d["to"], ""),
                        "rule": d["rule"],
                        "needs": [p for p in [phrase(d["must_be_true"], n)] if p]
                        + [phrase(c, n, negate=True) for c in d["must_be_false"]],
                    }
                    for d in p.decisions
                ],
                "calls": [
                    {"uuid": c, "name": objects.get(c, ("", "outside this export"))[1]}
                    for c in p.calls
                ],
                "tasks": [
                    {
                        "node": n,
                        "label": labels.get(n, ""),
                        "groups": [mapdb.assignee_name(a, objects) for a in groups],
                    }
                    for n, groups in p.tasks
                ],
            }
        )
    _, infeasible, truncated, loop_count = stats or (0, 0, 0, 0)
    return {
        "paths": out,
        "infeasible": infeasible,
        "truncated": bool(truncated),
        "loops": loop_count,
    }


def test_users(con: sqlite3.Connection, sid: int) -> list[dict[str, Any]]:
    """Every group a path's user task goes to, with how many tasks and processes need it."""
    objects = _names(con, sid)
    need: dict[str, dict[str, Any]] = {}
    on_paths = {
        (pm, node, g)
        for pm, rows in pathdb.read_all(con, sid)
        for r in rows
        for node, groups in r.tasks
        for g in groups or ["(assigned without a group)"]
    }
    for pm, _node, g in on_paths:
        who = mapdb.assignee_name(g, objects) if g.startswith(("_", "=")) or g in objects else g
        entry = need.setdefault(who, {"group": who, "tasks": 0, "processes": set()})
        entry["tasks"] += 1
        entry["processes"].add(objects.get(pm, ("", pm))[1])
    return sorted(
        ({**e, "processes": sorted(e["processes"]), "users_needed": 2} for e in need.values()),
        key=lambda e: -int(e["tasks"]),
    )


def decisions(con: sqlite3.Connection, sid: int, owner: str) -> list[dict[str, Any]]:
    """Decision points inside one object (its SAIL, or its gateway conditions)."""
    return [
        {
            "location": loc,
            "kind": k,
            "function": f,
            "condition": c,
            "outcomes": o,
            "literals": json.loads(lits),
        }
        for loc, k, f, c, o, lits in con.execute(
            "SELECT location, kind, function, condition, outcomes, literals FROM branches "
            "WHERE snapshot_id = ? AND owner_uuid = ? ORDER BY rowid",
            (sid, owner),
        )
    ]
