"""Layer 3 checks. A plain reachability search over the stored connections (no path engine)
says which nodes and gateway options exist; the stored paths must cover all of them."""

from __future__ import annotations

import json
import sqlite3
from collections import deque

from atg.layers.checks.layer1 import CheckResult

_GATEWAYS = ("core.3", "core.4", "core.5")


def run(con: sqlite3.Connection, sid: int) -> list[CheckResult]:
    names = dict(
        con.execute(
            "SELECT uuid, name FROM objects WHERE snapshot_id = ? AND type = 'processModel'", (sid,)
        )
    )
    want_nodes = want_options = got_nodes = got_options = 0
    missed_nodes: list[str] = []
    missed_options: list[str] = []
    no_path: list[str] = []
    for pm, name in names.items():
        reach, options = _reachable(con, sid, pm)
        steps: set[int] = set()
        taken: set[tuple[int, int]] = set()
        rows = con.execute(
            "SELECT steps, decisions FROM paths WHERE snapshot_id = ? AND pm_uuid = ?", (sid, pm)
        ).fetchall()
        for s, d in rows:
            steps |= set(json.loads(s))
            taken |= {(x["gateway"], x["to"]) for x in json.loads(d)}
        if reach and not rows:
            no_path.append(name)
        want_nodes += len(reach)
        got_nodes += len(reach & steps)
        want_options += len(options)
        got_options += len(options & taken)
        missed_nodes += [f"{name}: node {n}" for n in sorted(reach - steps)]
        missed_options += [f"{name}: gateway {a} -> {b}" for a, b in sorted(options - taken)]
    truncated = con.execute(
        "SELECT o.name FROM path_stats s JOIN objects o ON o.uuid = s.pm_uuid "
        "AND o.snapshot_id = s.snapshot_id WHERE s.snapshot_id = ? "
        "AND s.truncated = 1",
        (sid,),
    ).fetchall()
    return [
        CheckResult("every reachable node is on a path", want_nodes, got_nodes, missed_nodes[:20]),
        CheckResult(
            "every gateway option is on a path", want_options, got_options, missed_options[:20]
        ),
        CheckResult("every process has a path", len(names), len(names) - len(no_path), no_path),
        CheckResult(
            "no process cut off at the path limit", 0, len(truncated), [n for (n,) in truncated]
        ),
    ]


def _reachable(con: sqlite3.Connection, sid: int, pm: str) -> tuple[set[int], set[tuple[int, int]]]:
    types = dict(
        con.execute(
            "SELECT gui_id, type_id FROM nodes WHERE snapshot_id = ? AND pm_uuid = ?", (sid, pm)
        )
    )
    succ: dict[int, set[int]] = {}
    for a, b in con.execute(
        "SELECT from_gui, to_gui FROM flows WHERE snapshot_id = ? "
        "AND pm_uuid = ? AND kind = 'connection'",
        (sid, pm),
    ):
        if b in types:
            succ.setdefault(a, set()).add(b)
    starts = [n for n, t in types.items() if t == "core.0"] or [
        n for n in types if all(n not in s for s in succ.values())
    ]
    seen, queue = set(starts), deque(starts)
    while queue:
        for nxt in succ.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    options = {
        (g, t) for g in seen if types[g] in _GATEWAYS and len(succ.get(g, ())) > 1 for t in succ[g]
    }
    return seen, options
