"""Compact path storage: a row holds steps and choices only, and reading it back gives exactly
what the engine produced. Rows written in the old full-JSON format still read."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from atg import pathdb, store
from atg.layers import path_engine
from atg.layers.pipeline import run_layers
from atg.web import paths_api, tests_api
from tests.conftest import demo_export, single_root
from tests.demo import spec


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[sqlite3.Connection, int]:
    con = store.connect(Path(tmp_path_factory.mktemp("pdb")) / "map.db")
    sid, _ = run_layers(con, single_root(demo_export()))
    return con, sid


def _engine_view(con: sqlite3.Connection, sid: int, pm: str) -> list[pathdb.StoredPath]:
    g = pathdb.load_graph(con, sid, pm)
    out = []
    for no, p in enumerate(path_engine.enumerate_paths(g).paths, 1):
        decisions = [{**asdict(d), "must_be_false": list(d.must_be_false)} for d in p.decisions]
        calls = sorted({g.nodes[s].calls for s in p.steps if g.nodes[s].calls})
        tasks = [
            [s, list(g.nodes[s].assignees)]
            for s in p.steps
            if g.nodes[s].type_id == pathdb.USER_TASK
        ]
        out.append(pathdb.StoredPath(no, p.steps, decisions, calls, tasks, p.loops))
    return out


def test_reading_back_gives_what_the_engine_produced(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    for pm, rows in pathdb.read_all(con, sid):
        assert rows == _engine_view(con, sid, pm)


def test_rows_keep_no_condition_text(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    decisions, calls, tasks, choices = con.execute(
        "SELECT MAX(decisions), MAX(calls), MAX(tasks), MAX(LENGTH(choices)) FROM paths "
        "WHERE snapshot_id = ?",
        (sid,),
    ).fetchone()
    assert (decisions, calls, tasks) == (None, None, None)
    assert choices < 40


def test_old_full_json_rows_still_read(demo: tuple[sqlite3.Connection, int]) -> None:
    con, sid = demo
    want = pathdb.read(con, sid, spec.PM_SUBMIT)
    old = sid + 1000  # an imaginary older snapshot holding the same paths in the old format
    con.executemany(
        "INSERT INTO paths (snapshot_id, pm_uuid, path_no, steps, decisions, calls, tasks, loops)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                old,
                spec.PM_SUBMIT,
                p.no,
                *(json.dumps(x) for x in (p.steps, p.decisions, p.calls, p.tasks)),
                p.loops,
            )
            for p in want
        ],
    )
    assert pathdb.read(con, old, spec.PM_SUBMIT) == want
    con.execute("DELETE FROM paths WHERE snapshot_id = ?", (old,))


def test_the_cap_is_a_setting_and_recorded(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    sid, results = run_layers(con, single_root(demo_export()), max_paths=1)
    assert con.execute("SELECT max_paths FROM snapshots WHERE id = ?", (sid,)).fetchone() == (1,)
    cut = next(r for r in results if r.name == "no process cut off at the path limit")
    assert not cut.ok
    assert path_engine.MAX_PATHS == 20_000


def test_web_sends_a_path_count_and_one_path_on_demand(
    demo: tuple[sqlite3.Connection, int],
) -> None:
    con, sid = demo
    listing = {p["uuid"]: p for p in tests_api.tests(con, sid)["processes"]}
    submit = listing[spec.PM_SUBMIT]
    assert submit["path_count"] == len(submit["paths"]) >= 2
    one = paths_api.paths(con, sid, spec.PM_SUBMIT, 2)["paths"]
    assert [p["no"] for p in one] == [2]
    assert paths_api.paths(con, sid, spec.PM_SUBMIT, 999)["paths"] == []
