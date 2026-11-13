from __future__ import annotations

import atexit
import functools
import shutil
import sqlite3
import tempfile
from pathlib import Path

from atg import store
from atg.layers.checks import layer1
from atg.layers.checks.layer1 import CheckResult
from atg.read.ingest import read_snapshot
from atg.read.source import ExportRoot, find_roots
from tests.demo import build


@functools.cache
def demo_export() -> Path:
    """The made-up Expense Claims export (tests/demo), built once per test run."""
    folder = Path(tempfile.mkdtemp(prefix="atg-demo-")) / "Expense Claims"
    atexit.register(shutil.rmtree, folder.parent, True)
    return build(folder)


def single_root(path: Path) -> ExportRoot:
    roots = find_roots(path)
    assert len(roots) == 1, roots
    return roots[0]


def ingest(root: ExportRoot, db: Path) -> tuple[sqlite3.Connection, int]:
    con = store.connect(db)
    return con, store.save(con, read_snapshot(root))


def check(path: Path, db: Path) -> dict[str, CheckResult]:
    root = single_root(path)
    con, sid = ingest(root, db)
    return {r.name: r for r in layer1.run(con, sid, root.path)}


def failing(results: dict[str, CheckResult]) -> set[str]:
    return {name for name, r in results.items() if not r.ok}
