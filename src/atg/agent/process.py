"""A process for the agent: its diagram in short, and test paths that cover every gateway option
once (not every combination: 15 two-way gateways in a row are 32,768 combinations but about 35
options). Paths are built on the diagram itself, so they exist even where Layer 3 stopped at
its path limit; contradictions between conditions are not checked here (Layer 3 does that).
"""

from __future__ import annotations

import itertools
import json
from collections import deque
from typing import Any

from atg.agent.atlas import Atlas
from atg.agent.effects import TASK, assignee, node_effects
from atg.sail.explain import phrase

Graph = dict[int, list[int]]
START, END = "core.0", "core.1"


def _route(succ: Graph, start: int, goal: set[int]) -> list[int]:
    """Shortest node list from start to any goal node ([] when none is reachable)."""
    parent: dict[int, int] = {}
    seen, queue = {start}, deque([start])
    while queue:
        cur = queue.popleft()
        if cur in goal:
            path = [cur]
            while path[-1] != start:
                path.append(parent[path[-1]])
            return path[::-1]
        for nxt in succ.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                parent[nxt] = cur
                queue.append(nxt)
    return []


def covering_paths(atlas: Atlas, pm: str) -> dict[str, Any]:
    nodes = {
        g: (t, lab or tn)
        for g, t, tn, lab in atlas.con.execute(
            "SELECT gui_id, type_id, type_name, label FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ?",
            (atlas.sid, pm),
        )
    }
    succ: Graph = {}
    options: list[tuple[int, int, str, str]] = []
    for a, b, kind, label, cond in atlas.con.execute(
        "SELECT from_gui, to_gui, kind, label, condition FROM flows "
        "WHERE snapshot_id = ? AND pm_uuid = ? ORDER BY rowid",
        (atlas.sid, pm),
    ):
        succ.setdefault(a, []).append(b)
        if kind.startswith("gateway"):
            say = phrase(cond, atlas.names) if cond else "none of the other conditions hold"
            options.append((a, b, label or ("otherwise" if not cond else ""), say or cond))
    starts = [g for g, (t, _) in nodes.items() if t == START] or sorted(nodes)[:1]
    ends = {g for g, (t, _) in nodes.items() if t == END or not succ.get(g)}
    effects = node_effects(atlas, pm)
    covered: set[tuple[int, int]] = set()
    paths: list[dict[str, Any]] = []
    unreachable = []
    for gw, to, label, say in options:
        if (gw, to) in covered:
            continue
        head = next((p for s in starts if (p := _route(succ, s, {gw}))), [])
        tail = _route(succ, to, ends)
        if not head or not tail:
            unreachable.append(f"{nodes.get(gw, ('', gw))[1]} -> {label or to}")
            continue
        steps = head + tail
        new = {(x, y) for x, y in itertools.pairwise(steps)} & {(o[0], o[1]) for o in options}
        covered |= new
        paths.append(
            {
                "covers": f"{nodes[gw][1]}: {label or nodes.get(to, ('', to))[1]} ({say})",
                "choices": [
                    f"{nodes[x][1]} -> {o[2] or nodes.get(y, ('', y))[1]}: {o[3]}"
                    for x, y in itertools.pairwise(steps)
                    for o in options
                    if (o[0], o[1]) == (x, y)
                ],
                "steps": [nodes.get(s, ("", str(s)))[1] for s in steps],
                "changes": list(dict.fromkeys(e for s in steps for e in effects.get(s, []))),
            }
        )
    return {
        "options": len(options),
        "paths": paths,
        "not_reachable": unreachable,
        "note": "one path per gateway option not yet covered; conditions are not cross-checked",
    }


def summary(atlas: Atlas, pm: str) -> dict[str, Any]:
    rows = list(
        atlas.con.execute(
            "SELECT gui_id, type_id, type_name, label, assignees FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ? ORDER BY gui_id",
            (atlas.sid, pm),
        )
    )
    stats = atlas.con.execute(
        "SELECT feasible, infeasible, truncated FROM path_stats "
        "WHERE snapshot_id = ? AND pm_uuid = ?",
        (atlas.sid, pm),
    ).fetchone()
    gateways = atlas.con.execute(
        "SELECT COUNT(DISTINCT from_gui) FROM flows WHERE snapshot_id = ? AND pm_uuid = ? "
        "AND kind LIKE 'gateway%'",
        (atlas.sid, pm),
    ).fetchone()[0]
    return {
        "nodes": len(rows),
        "gateways": gateways,
        "tasks": [
            {"task": lab or tn, "for": [assignee(a, atlas) for a in json.loads(asg or "[]")]}
            for _, t, tn, lab, asg in rows
            if t == TASK
        ],
        "all_combinations": None
        if not stats
        else {"found": stats[0], "contradictory": stats[1], "stopped_at_limit": bool(stats[2])},
    }
