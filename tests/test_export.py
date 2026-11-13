"""Every layer on the demo export: every check passes, the numbers are frozen, and the same
export marked as Appian 20 to 26 reads the same. Versions below 20 are refused."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from atg import store
from atg.layers.pipeline import run_layers
from atg.read.select import UnsupportedVersionError, reader_for
from atg.read.source import ExportRoot, find_roots
from tests.conftest import check, demo_export, failing, single_root


def test_every_check_passes(tmp_path: Path) -> None:
    assert failing(check(demo_export(), tmp_path / "map.db")) == set()


def test_demo_numbers_are_frozen(tmp_path: Path) -> None:
    """Counted independently of the parser. A change here must be explained."""
    r = check(demo_export(), tmp_path / "map.db")
    assert r["data files -> object or unknown"].actual == 24
    assert r["process nodes"].actual == 14
    assert r["connections"].actual == 13
    assert r["gateway rules"].actual == 2
    assert r["gateway defaults"].actual == 2
    assert r['canonical #" refs'].actual == 65
    assert r["UUID sweep (every token classified)"].actual == 118
    assert r["objects: contentHaul"].actual == 12
    assert r["objects: processModelHaul"].actual == 3


@pytest.mark.parametrize("version", ["20.1.88.0", "22.4.250.0", "24.2.270.0", "26.6.75.0"])
def test_every_layer_passes_from_appian_20(version: str, tmp_path: Path) -> None:
    export = tmp_path / "export"
    shutil.copytree(demo_export(), export)
    (export / "META-INF" / "MANIFEST.MF").write_text(
        f"Appian-Version: {version}\n", encoding="utf-8"
    )
    root = single_root(export)
    assert root.appian_version == version
    _, results = run_layers(store.connect(tmp_path / "map.db"), root)
    assert [r.name for r in results if not r.ok] == []


def test_versions_below_20_are_refused() -> None:
    for old in ("7.9.0.0", "17.4.29.0", "19.4.1.0"):
        with pytest.raises(UnsupportedVersionError):
            reader_for(ExportRoot(Path("x"), old))
    assert reader_for(ExportRoot(Path("x"), "20.1.88.0")) == "haul"


def test_manifest_one_level_deeper_is_found(tmp_path: Path) -> None:
    """Patch and multi-app exports keep it at META-INF/<app id>/MANIFEST.MF."""
    nested = tmp_path / "export" / "META-INF" / "_a-0000d3e0-0000-8000-9000-000000000000_1"
    nested.mkdir(parents=True)
    (nested / "MANIFEST.MF").write_text("Appian-Version: 25.3.0.1\n", encoding="utf-8")
    assert [(r.path.name, r.major) for r in find_roots(tmp_path)] == [("export", 25)]


def test_unsafe_zips_are_refused(tmp_path: Path) -> None:
    """A zip entry must not land outside its folder ("zip slip")."""
    import zipfile

    from atg.read.source import UnsafeZipError

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escaped.txt", "x")
    with pytest.raises(UnsafeZipError):
        find_roots(bad)
    assert not (tmp_path / "escaped.txt").exists()


def test_a_zipped_export_is_read(tmp_path: Path) -> None:
    zipped = shutil.make_archive(str(tmp_path / "claims"), "zip", demo_export())
    (root,) = find_roots(Path(zipped))
    assert root.appian_version == "25.4.0.0"
