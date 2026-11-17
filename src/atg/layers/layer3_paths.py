"""Layer 3: load each process from the map, enumerate its paths, store them (one insert per
process, in the compact row format of `atg.pathdb`)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from atg import pathdb
from atg.layers import path_engine
from atg.layers.path_engine import Result

ProcessProgress = Callable[[int, int], None]


def run(
    con: sqlite3.Connection,
    sid: int,
    on_process: ProcessProgress | None = None,
    max_paths: int | None = None,
) -> None:
    cap = path_engine.MAX_PATHS if max_paths is None else max_paths
    with con:
        con.execute("UPDATE snapshots SET max_paths = ? WHERE id = ?", (cap, sid))
    pms = [
        r[0]
        for r in con.execute(
            "SELECT uuid FROM objects WHERE snapshot_id = ? AND type = 'processModel' "
            "ORDER BY name",
            (sid,),
        )
    ]
    for done, pm in enumerate(pms, 1):
        if on_process is not None:
            on_process(done, len(pms))
        g = pathdb.load_graph(con, sid, pm)
        result = path_engine.enumerate_paths(g, cap)
        with con:
            con.executemany(pathdb.INSERT_SQL, pathdb.rows(sid, pm, g, result.paths))
            con.execute("INSERT INTO path_stats VALUES (?,?,?,?,?,?)", _stats(sid, pm, result))


def _stats(sid: int, pm: str, r: Result) -> tuple[object, ...]:
    return (sid, pm, len(r.paths), r.infeasible, int(r.truncated), len(r.back_edges))
