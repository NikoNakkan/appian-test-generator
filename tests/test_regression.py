"""Regression impact on the demo export with planted changes: what changed, what it affects,
and which tests rerun or are skipped."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from atg import store
from atg.layers.pipeline import run_layers
from atg.regression import impact as regression
from atg.regression import verdicts
from tests.conftest import demo_export, single_root
from tests.demo import build_next


def _import(con: sqlite3.Connection, path: Path) -> int:
    sid, _ = run_layers(con, single_root(path))
    return sid


def _copy(src: Path, tmp: Path) -> Path:
    target = tmp / "next"
    shutil.copytree(src, target, ignore=shutil.ignore_patterns(".git"))
    return target


def _edit(export: Path, rel: str, old: str, new: str) -> None:
    path = export / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (rel, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _rel(con: sqlite3.Connection, sid: int, name: str) -> tuple[str, str]:
    uuid, path = con.execute(
        "SELECT uuid, path FROM objects WHERE snapshot_id = ? AND name = ?", (sid, name)
    ).fetchone()
    return str(uuid), str(path)


def test_same_export_twice_changes_nothing(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    a, b = _import(con, demo_export()), _import(con, demo_export())
    assert regression.base_for(con, b) == a
    r = verdicts.report(con, a, b)
    assert r["changes"] == [] and r["affected"] == [] and r["verdicts"] == []


def test_changed_rule_flags_its_users_and_only_their_tests(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    a = _import(con, demo_export())
    used_rule = con.execute(
        "SELECT o.name, o.path FROM objects o JOIN refs r ON r.target = o.uuid AND "
        "r.snapshot_id = o.snapshot_id JOIN nodes n ON n.pm_uuid = r.source_uuid AND "
        "n.snapshot_id = o.snapshot_id WHERE o.snapshot_id = ? AND o.type = 'rule' LIMIT 1",
        (a,),
    ).fetchone()
    name, rel = used_rule
    nxt = _copy(demo_export(), tmp_path)
    _edit(nxt, rel, "<definition>", "<definition>/* edited */")
    b = _import(con, nxt)
    r = verdicts.report(con, a, b)
    assert [(c["status"], c["name"]) for c in r["changes"]] == [("changed", name)]
    assert r["affected"] and all(name in x["via"] for x in r["affected"])
    paths = [v for v in r["verdicts"] if v["kind"] == "path"]
    assert paths and all(v["verdict"] == "rerun" for v in paths)
    assert all(any(name in reason for reason in v["reasons"]) for v in paths)
    assert r["summary"]["path"].get("skip", 0) > 0  # untouched paths are not rerun
    assert any(
        v["kind"] == "rule" and v["item"] == name and v["verdict"] == "redesign"
        for v in r["verdicts"]
    )


def test_removed_object_flags_the_objects_that_used_it(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    a = _import(con, demo_export())
    used = con.execute(
        "SELECT o.name, o.path FROM objects o WHERE o.snapshot_id = ? AND o.type = 'rule' AND "
        "EXISTS (SELECT 1 FROM refs r JOIN objects s ON s.uuid = r.source_uuid AND "
        "s.snapshot_id = r.snapshot_id WHERE r.snapshot_id = o.snapshot_id AND r.target = o.uuid "
        "AND s.type IN ('rule', 'interface')) LIMIT 1",
        (a,),
    ).fetchone()
    nxt = _copy(demo_export(), tmp_path)
    (nxt / used[1]).unlink()
    b = _import(con, nxt)
    r = verdicts.report(con, a, b)
    assert ("removed", used[0]) in [(c["status"], c["name"]) for c in r["changes"]]
    assert any(used[0] in x["via"] for x in r["affected"])


def test_next_release_is_frozen(tmp_path: Path) -> None:
    """The demo's three planted edits (tests/demo NEXT_RELEASE): a constant, a gateway
    condition and a rule. A change in these numbers must be explained."""
    con = store.connect(tmp_path / "map.db")
    a = _import(con, demo_export())
    b = _import(con, build_next(tmp_path / "next"))
    r = verdicts.report(con, a, b)
    assert sorted(c["name"] for c in r["changes"]) == [
        "EXP_APPROVAL_LIMIT",
        "EXP_LineTotal",
        "EXP_SubmitClaim",
    ]
    assert sorted(x["name"] for x in r["affected"]) == [
        "EXP_ClaimForm",
        "EXP_ClaimsList",
        "EXP_Dashboard",
        "EXP_NeedsApproval",
    ]
    assert r["summary"]["path"] == {"rerun": 3, "skip": 2}
    # Starting a process is not a dependency on its insides: callers of the changed
    # process are not flagged because of it.
    assert not any(x["via"][:1] == ["EXP_SubmitClaim"] for x in r["affected"])
    gateway = [v for v in r["verdicts"] if v["item"] in {"path 2", "path 3"}]
    assert gateway and all(any("changed" in why for why in v["reasons"]) for v in gateway)
