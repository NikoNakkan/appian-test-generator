"""Layer 2 on the demo export: checks pass, the numbers are frozen, and each check can fail."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from atg import store
from atg.layers.checks.layer1 import CheckResult
from atg.layers.pipeline import run_layers
from atg.sail import branches, printer
from tests.conftest import demo_export, single_root


def _layer2(path: Path, db: Path) -> dict[str, CheckResult]:
    _, results = run_layers(store.connect(db), single_root(path))
    names = {
        "SAIL sources parsed",
        "round-trip identical",
        "if() decisions found",
        "forEach loops found",
    }
    return {r.name: r for r in results if r.name in names}


def _failing(results: dict[str, CheckResult]) -> set[str]:
    return {n for n, r in results.items() if not r.ok}


def test_layer2_numbers_are_frozen(tmp_path: Path) -> None:
    """Counted independently of the parser on 2026-11-08. A change here must be explained."""
    r = _layer2(demo_export(), tmp_path / "map.db")
    assert _failing(r) == set()
    assert r["SAIL sources parsed"].actual == 12
    assert r["if() decisions found"].actual == 3
    assert r["forEach loops found"].actual == 2


@pytest.fixture
def export(tmp_path: Path) -> Path:
    target = tmp_path / "export"
    shutil.copytree(demo_export(), target)
    return target


def test_unparseable_rule_is_caught(export: Path, tmp_path: Path) -> None:
    rule = next(
        p for p in (export / "content").glob("*.xml") if "<definition>" in p.read_text("utf-8")
    )
    text = rule.read_text(encoding="utf-8")
    rule.write_text(text.replace("<definition>", "<definition>if(((", 1), encoding="utf-8")
    assert "SAIL sources parsed" in _failing(_layer2(export, tmp_path / "map.db"))


def test_printer_losing_trailing_commas_is_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = printer._args
    monkeypatch.setattr(printer, "_args", lambda a: real(type(a)(a.items, False)))
    assert "round-trip identical" in _failing(_layer2(export, tmp_path / "map.db"))


def test_missing_if_decisions_are_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = branches.find
    monkeypatch.setattr(branches, "find", lambda e: [b for b in real(e) if b.kind != "if"])
    monkeypatch.setattr("atg.layers.layer2_sail.find", branches.find)
    assert "if() decisions found" in _failing(_layer2(export, tmp_path / "map.db"))


def test_missing_loops_are_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = branches.find
    monkeypatch.setattr(
        "atg.layers.layer2_sail.find", lambda e: [b for b in real(e) if b.kind != "loop"]
    )
    assert "forEach loops found" in _failing(_layer2(export, tmp_path / "map.db"))
