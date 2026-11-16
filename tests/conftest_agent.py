"""Shared setup for the analysis tests: the agent demo ingested into a fresh map per module."""

from __future__ import annotations

from pathlib import Path

from atg import store
from atg.agent import atlas
from atg.layers.pipeline import run_layers
from tests import agentdemo
from tests.conftest import single_root


def fresh(tmp: Path) -> atlas.Atlas:
    folder = agentdemo.build(tmp)
    con = store.connect(tmp / "map.db")
    sid, results = run_layers(con, single_root(folder))
    assert all(r.ok for r in results), [r.name for r in results if not r.ok]
    return atlas.load(con, sid)


def reimport(at: atlas.Atlas) -> atlas.Atlas:
    """The same export imported again: a second snapshot in the same map."""
    folder = Path(
        at.con.execute("SELECT source FROM snapshots WHERE id = ?", (at.sid,)).fetchone()[0]
    )
    sid, _ = run_layers(at.con, single_root(folder))
    return atlas.load(at.con, sid)
