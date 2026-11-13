"""Every Layer 1 check must be able to fail. Each test plants one bug and expects a FAIL.

Bugs are planted either in the parser (monkeypatch) or in a copy of a real export.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from atg.model import Flow, FlowKind
from atg.read import process, scan
from tests.conftest import check, demo_export, failing


@pytest.fixture
def export(tmp_path: Path) -> Path:
    target = tmp_path / "export"
    shutil.copytree(demo_export(), target)
    return target


def test_parser_dropping_a_connection_is_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = process._connections

    def lossy(node: object, gui: int) -> list[Flow]:
        return real(node, gui)[1:]  # type: ignore[arg-type]

    monkeypatch.setattr(process, "_connections", lossy)
    assert "connections" in failing(check(export, tmp_path / "map.db"))


def test_parser_dropping_gateway_rules_is_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = process._gateway_rules

    def no_rules(ac: object, gui: int) -> list[Flow]:
        flows = real(ac, gui)  # type: ignore[arg-type]
        return [f for f in flows if f.kind is not FlowKind.GATEWAY_RULE]

    monkeypatch.setattr(process, "_gateway_rules", no_rules)
    assert "gateway rules" in failing(check(export, tmp_path / "map.db"))


def test_parser_ignoring_attributes_is_caught_by_the_sweep(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = scan._scan_value

    def skip_attrs(
        out: scan.FileScan,
        self_uuid: str,
        text: str,
        context: str,
        *,
        version: bool,
        defining: bool,
    ) -> None:
        if not context.startswith("@"):
            real(out, self_uuid, text, context, version=version, defining=defining)

    monkeypatch.setattr(scan, "_scan_value", skip_attrs)
    assert "UUID sweep (every token classified)" in failing(check(export, tmp_path / "map.db"))


def test_uuid_hidden_where_the_parser_cannot_see_is_caught(export: Path, tmp_path: Path) -> None:
    rule = next((export / "content").glob("*.xml"))
    text = rule.read_text(encoding="utf-8")
    hidden = "<!-- d3e0ffff-0000-4000-8000-00000000ffff -->"
    rule.write_text(text.replace("<name>", hidden + "<name>", 1), encoding="utf-8")
    assert "UUID sweep (every token classified)" in failing(check(export, tmp_path / "map.db"))


def test_new_node_type_is_reported_as_unknown(export: Path, tmp_path: Path) -> None:
    pm = next((export / "processModel").glob("*.xml"))
    text = pm.read_text(encoding="utf-8")
    pm.write_text(
        text.replace("<local-id>core.0</local-id>", "<local-id>core.99</local-id>", 1),
        encoding="utf-8",
    )
    assert "unknowns" in failing(check(export, tmp_path / "map.db"))


def test_unknown_object_kind_is_reported(export: Path, tmp_path: Path) -> None:
    (export / "content" / "new.xml").write_text(
        "<futureThingHaul><futureThing><uuid>x</uuid></futureThing></futureThingHaul>",
        encoding="utf-8",
    )
    assert "unknowns" in failing(check(export, tmp_path / "map.db"))


def test_parser_losing_an_object_is_caught(
    export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atg.read import haul

    real = haul.read_file
    calls = {"n": 0}

    def drop_first(path: Path, rel: str):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return (None, [], None) if calls["n"] == 1 else real(path, rel)

    monkeypatch.setattr(haul, "read_file", drop_first)
    assert "data files -> object or unknown" in failing(check(export, tmp_path / "map.db"))
