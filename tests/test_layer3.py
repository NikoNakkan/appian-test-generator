"""Layer 3 on the demo export: checks pass, the numbers are frozen, and each check can fail."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atg import store
from atg.layers import path_engine as engine
from atg.layers.checks.layer1 import CheckResult
from atg.layers.pipeline import run_layers
from tests.conftest import demo_export, single_root


def _layer3(path: Path, db: Path) -> tuple[dict[str, CheckResult], sqlite3.Connection, int]:
    con = store.connect(db)
    sid, results = run_layers(con, single_root(path))
    names = {
        "every reachable node is on a path",
        "every gateway option is on a path",
        "every process has a path",
        "no process cut off at the path limit",
    }
    return {r.name: r for r in results if r.name in names}, con, sid


def _failing(results: dict[str, CheckResult]) -> set[str]:
    return {n for n, r in results.items() if not r.ok}


def test_layer3_numbers_are_frozen(tmp_path: Path) -> None:
    """Counted on 2026-11-08. A change here must be explained."""
    r, con, sid = _layer3(demo_export(), tmp_path / "map.db")
    assert _failing(r) == set()
    assert r["every reachable node is on a path"].actual == 14
    assert r["every gateway option is on a path"].actual == 4
    feasible, infeasible = con.execute(
        "SELECT SUM(feasible), SUM(infeasible) FROM path_stats WHERE snapshot_id = ?", (sid,)
    ).fetchone()
    assert (feasible, infeasible) == (5, 0)


def test_engine_skipping_options_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = engine.gateway_options
    monkeypatch.setattr(engine, "gateway_options", lambda g, n, nx: real(g, n, nx)[:1])
    r, _, _ = _layer3(demo_export(), tmp_path / "map.db")
    assert "every gateway option is on a path" in _failing(r)


def test_engine_stopping_early_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "STARTS", frozenset({"no-such-start"}))
    monkeypatch.setattr(engine, "starts", lambda g: [])
    r, _, _ = _layer3(demo_export(), tmp_path / "map.db")
    assert {"every reachable node is on a path", "every process has a path"} <= _failing(r)


def test_path_limit_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "MAX_PATHS", 1)
    r, _, _ = _layer3(demo_export(), tmp_path / "map.db")
    assert "no process cut off at the path limit" in _failing(r)
