"""Layer 3: load each process from the map, enumerate its paths, store them."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict

from atg.layers.path_engine import Graph, Node, Path, Result, Rule, enumerate_paths

ProcessProgress = Callable[[int, int], None]


def load_graph(con: sqlite3.Connection, sid: int, pm: str) -> Graph:
    nodes = {
        gui: Node(
            gui,
            type_id,
            label or type_name,
            tuple(json.loads(w or "[]")),
            calls or "",
            tuple(json.loads(a or "[]")),
        )
        for gui, type_id, type_name, label, w, calls, a in con.execute(
            "SELECT gui_id, type_id, type_name, label, writes, calls, assignees FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    }
    succ: dict[int, list[int]] = {}
    rules: dict[int, list[Rule]] = {}
    defaults: dict[int, int] = {}
    for a, b, kind, label, cond in con.execute(
        "SELECT from_gui, to_gui, kind, label, condition FROM flows "
        "WHERE snapshot_id = ? AND pm_uuid = ? ORDER BY rowid",
        (sid, pm),
    ):
        if kind == "connection" and b in nodes and b not in succ.get(a, []):
            succ.setdefault(a, []).append(b)
        elif kind == "gateway_rule":
            rules.setdefault(a, []).append(Rule(b, cond or "", label or ""))
        elif kind == "gateway_default":
            defaults[a] = b
    return Graph(nodes, succ, rules, defaults)


def run(con: sqlite3.Connection, sid: int, on_process: ProcessProgress | None = None) -> None:
    pms = [
        r[0]
        for r in con.execute(
            "SELECT uuid FROM objects WHERE snapshot_id = ? AND type = 'processModel' "
            "ORDER BY name",
            (sid,),
        )
    ]
    path_rows, stat_rows = [], []
    for done, pm in enumerate(pms, 1):
        if on_process is not None:
            on_process(done, len(pms))
        g = load_graph(con, sid, pm)
        result = enumerate_paths(g)
        path_rows += [_path_row(sid, pm, i, g, p) for i, p in enumerate(result.paths, 1)]
        stat_rows.append(_stats(sid, pm, result))
    with con:
        con.executemany("INSERT INTO paths VALUES (?,?,?,?,?,?,?,?)", path_rows)
        con.executemany("INSERT INTO path_stats VALUES (?,?,?,?,?,?)", stat_rows)


def _path_row(sid: int, pm: str, no: int, g: Graph, p: Path) -> tuple[object, ...]:
    calls = sorted({g.nodes[s].calls for s in p.steps if s in g.nodes and g.nodes[s].calls})
    tasks = [
        [s, list(g.nodes[s].assignees)]
        for s in p.steps
        if s in g.nodes and g.nodes[s].type_id == "internal.17"
    ]
    return (
        sid,
        pm,
        no,
        json.dumps(p.steps),
        json.dumps([asdict(d) for d in p.decisions]),
        json.dumps(calls),
        json.dumps(tasks),
        p.loops,
    )


def _stats(sid: int, pm: str, r: Result) -> tuple[object, ...]:
    return (sid, pm, len(r.paths), r.infeasible, int(r.truncated), len(r.back_edges))
