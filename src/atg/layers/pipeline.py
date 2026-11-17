"""One export root through every built layer: read, save, parse, check, keep the results."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from atg import store
from atg.layers import layer2_sail, layer3_paths, layer4_features
from atg.layers.checks import layer1 as checks1
from atg.layers.checks import layer2 as checks2
from atg.layers.checks import layer3 as checks3
from atg.layers.checks import layer4 as checks4
from atg.layers.checks.layer1 import CheckResult
from atg.read.ingest import read_snapshot
from atg.read.source import ExportRoot

# (stage, done, total): reading, saving, parsing SAIL, finding paths, grouping features, checking.
Progress = Callable[[str, int, int], None]


def run_layers(
    con: sqlite3.Connection,
    root: ExportRoot,
    progress: Progress | None = None,
    max_paths: int | None = None,
) -> tuple[int, list[CheckResult]]:
    """Returns the snapshot id and every check result, Layer 1 first. `max_paths` caps the test
    paths kept per process (default `path_engine.MAX_PATHS`); the map records the cap used."""
    report = progress or (lambda stage, done, total: None)
    snap = read_snapshot(root, on_file=lambda done, total: report("reading", done, total))
    report("saving", 0, 1)
    sid = store.save(con, snap)
    report("checking", 0, 1)
    results1 = checks1.run(con, sid, root.path)
    layer2_sail.run(con, sid, on_source=lambda done, total: report("parsing SAIL", done, total))
    report("checking", 0, 1)
    results2 = checks2.run(con, sid)
    layer3_paths.run(
        con,
        sid,
        on_process=lambda done, total: report("finding paths", done, total),
        max_paths=max_paths,
    )
    report("checking", 0, 1)
    results3 = checks3.run(con, sid)
    report("grouping features", 0, 1)
    layer4_features.run(con, sid)
    results4 = checks4.run(con, sid)
    with con:
        con.executemany(
            "INSERT INTO check_results VALUES (?,?,?,?,?,?,?)",
            [
                (sid, layer, r.name, r.expected, r.actual, int(r.ok), "\n".join(r.details))
                for layer, results in ((1, results1), (2, results2), (3, results3), (4, results4))
                for r in results
            ],
        )
    report("checking", 1, 1)
    return sid, results1 + results2 + results3 + results4
