"""Layer 4 on the demo export: checks pass, numbers frozen, checks can fail, Excel round trip."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

from atg import approvals, store
from atg.approvals import feature_list
from atg.layers import feature_engine as engine
from atg.layers.checks.layer1 import CheckResult
from atg.layers.pipeline import run_layers
from tests.conftest import demo_export, single_root

NAMES = {
    "every entry point starts a feature",
    "every process is in a feature",
    "features include the subprocesses they call",
    "every feature starts at a real object",
}


def _layer4(path: Path, db: Path) -> tuple[dict[str, CheckResult], sqlite3.Connection, int]:
    con = store.connect(db)
    sid, results = run_layers(con, single_root(path))
    return {r.name: r for r in results if r.name in NAMES}, con, sid


def _failing(results: dict[str, CheckResult]) -> set[str]:
    return {n for n, r in results.items() if not r.ok}


def test_layer4_numbers_are_frozen(tmp_path: Path) -> None:
    """Counted on 2026-11-08. A change here must be explained."""
    r, con, sid = _layer4(demo_export(), tmp_path / "map.db")
    assert _failing(r) == set()
    assert r["features include the subprocesses they call"].actual == 1
    assert len(feature_list(con, sid)) == 5


def test_not_following_subprocesses_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "EXPAND", engine.EXPAND - {"processModel"})
    r, _, _ = _layer4(demo_export(), tmp_path / "map.db")
    assert "features include the subprocesses they call" in _failing(r)


def test_dropping_an_entry_point_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = engine.entry_points
    monkeypatch.setattr(engine, "entry_points", lambda con, sid: real(con, sid)[1:])
    r, _, _ = _layer4(demo_export(), tmp_path / "map.db")
    assert "every entry point starts a feature" in _failing(r)


def _fill(sheet: bytes, rows: dict[int, tuple[str, str, str]]) -> bytes:
    wb = load_workbook(io.BytesIO(sheet))
    ws = wb["Features"]
    for row, (decision, new_name, who) in rows.items():
        ws.cell(row, 7, decision)
        ws.cell(row, 8, new_name)
        ws.cell(row, 9, who)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_excel_round_trip_is_strict(tmp_path: Path) -> None:
    _, con, sid = _layer4(demo_export(), tmp_path / "map.db")
    sheet = approvals.export_sheet(con, sid)
    filled = _fill(
        sheet,
        {
            2: ("approved", "", "Ana"),
            3: ("edit", "", "Ana"),  # edit without a new name: refused
            4: ("yes", "", "Ana"),  # not a dropdown value: refused
            5: ("rejected", "", ""),  # no name: refused
            6: ("edit", "Better name", "Ana"),
        },
    )
    result = approvals.import_sheet(con, sid, filled)
    assert result.applied == 2
    assert len(result.problems) == 3
    assert result.skipped_blank == len(feature_list(con, sid)) - 5
    statuses = sorted(f["approval"]["status"] for f in feature_list(con, sid))
    assert statuses.count("approved") == 1 and statuses.count("edit") == 1
    assert any(f["name"] == "Better name" for f in feature_list(con, sid))


def test_changed_feature_needs_re_approval_and_stale_rows_are_refused(tmp_path: Path) -> None:
    _, con, sid = _layer4(demo_export(), tmp_path / "map.db")
    sheet = approvals.export_sheet(con, sid)
    approvals.import_sheet(con, sid, _fill(sheet, {2: ("approved", "", "Ana")}))
    key = load_workbook(io.BytesIO(sheet))["Features"].cell(2, 10).value
    with con:  # the feature changes: one member disappears
        con.execute(
            "DELETE FROM feature_members WHERE rowid = (SELECT MIN(rowid) FROM "
            "feature_members WHERE snapshot_id = ? AND key = ?)",
            (sid, key),
        )
    status = next(f["approval"]["status"] for f in feature_list(con, sid) if f["key"] == key)
    assert status == "needs re-approval"
    again = approvals.import_sheet(con, sid, _fill(sheet, {2: ("approved", "", "Ana")}))
    assert again.applied == 0 and "changed since" in again.problems[0]
