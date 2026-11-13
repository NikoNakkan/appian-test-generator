"""Read-only queries over the map, shaped for the web UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from atg.approvals import feature_list

# Containers, not logic: left out of the dependency view.
_CONTAINERS = (
    "rulesFolder",
    "folder",
    "processModelFolder",
    "knowledgeCenter",
    "application",
    "document",
)

LAYERS = [
    (1, "Inventory and references", "Every object, reference, process node and flow in SQL."),
    (2, "SAIL parser", "Branches inside every rule and interface."),
    (3, "Process paths", "Every feasible path through each process."),
    (4, "Features", "Entry points grouped into business features."),
    (5, "Test design and runs", "Tests generated, recorded and run on dev."),
    (6, "Expected results", "Results approved by a person and frozen."),
]


def _rows(con: sqlite3.Connection, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return con.execute(sql, args).fetchall()


def _one(con: sqlite3.Connection, sql: str, *args: object) -> int:
    row = con.execute(sql, args).fetchone()
    return int(row[0] or 0) if row else 0


def snapshots(con: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for sid, source, version, created in _rows(
        con, "SELECT id, source, appian_version, created_at FROM snapshots ORDER BY id DESC"
    ):
        passed = _one(con, "SELECT SUM(ok) FROM check_results WHERE snapshot_id = ?", sid)
        total = _one(con, "SELECT COUNT(*) FROM check_results WHERE snapshot_id = ?", sid)
        apps = [
            n
            for (n,) in _rows(
                con,
                "SELECT name FROM objects WHERE snapshot_id = ? "
                "AND type = 'application' ORDER BY name",
                sid,
            )
        ]
        out.append(
            {
                "id": sid,
                "name": " + ".join(apps) or Path(source).name,  # the app's own name, else folder
                "source": source,
                "version": version,
                "created": created,
                "passed": passed,
                "checks": total,
                **_counts(con, sid),
            }
        )
    return out


def _counts(con: sqlite3.Connection, sid: int) -> dict[str, int]:
    def q(sql: str) -> int:
        return _one(con, sql, sid)

    return {
        "objects": q("SELECT COUNT(*) FROM objects WHERE snapshot_id = ?"),
        "processes": q(
            "SELECT COUNT(*) FROM objects WHERE snapshot_id = ? AND type='processModel'"
        ),
        "nodes": q("SELECT COUNT(*) FROM nodes WHERE snapshot_id = ?"),
        "flows": q("SELECT COUNT(*) FROM flows WHERE snapshot_id = ? AND kind='connection'"),
        "gateway_rules": q(
            "SELECT COUNT(*) FROM flows WHERE snapshot_id = ? AND kind='gateway_rule'"
        ),
        "references": q(
            "SELECT COALESCE(SUM(occurrences),0) FROM refs WHERE snapshot_id = ? "
            "AND kind NOT IN ('platform','self')"
        ),
        "external": q(
            "SELECT COUNT(DISTINCT target) FROM refs WHERE snapshot_id = ? AND resolved = 0"
        ),
        "unknowns": q("SELECT COUNT(*) FROM unknowns WHERE snapshot_id = ?"),
        "sail_parsed": q("SELECT COUNT(*) FROM sail_parse WHERE snapshot_id = ? AND ok = 1"),
        "decisions": q("SELECT COUNT(*) FROM branches WHERE snapshot_id = ?"),
        "paths": q("SELECT COALESCE(SUM(feasible),0) FROM path_stats WHERE snapshot_id = ?"),
    }


def checks(con: sqlite3.Connection, sid: int) -> list[dict[str, Any]]:
    return [
        {
            "layer": layer,
            "name": n,
            "expected": e,
            "actual": a,
            "ok": bool(ok),
            "details": d.splitlines() if d else [],
        }
        for layer, n, e, a, ok, d in _rows(
            con,
            "SELECT layer, name, expected, actual, ok, details FROM check_results "
            "WHERE snapshot_id = ? ORDER BY rowid",
            sid,
        )
    ]


def progress(con: sqlite3.Connection, sid: int | None) -> dict[str, Any]:
    """Layer status for one snapshot, plus how its numbers moved since the previous run."""
    layers = []
    all_checks = checks(con, sid) if sid is not None else []
    for n, name, goal in LAYERS:
        status, detail = "not started", ""
        rows = [r for r in all_checks if r["layer"] == n]
        if rows:
            ok = sum(r["ok"] for r in rows)
            status = "passing" if ok == len(rows) else "failing"
            detail = f"{ok} of {len(rows)} checks pass"
            if n == 4 and sid is not None:
                fs = feature_list(con, sid)
                done = sum(f["approval"]["status"] in {"approved", "edit", "rejected"} for f in fs)
                detail += f" · {done} of {len(fs)} features decided by a person"
        layers.append({"layer": n, "name": name, "goal": goal, "status": status, "detail": detail})
    kinds = (
        _rows(
            con,
            "SELECT kind, COUNT(*), SUM(outcomes) FROM branches WHERE snapshot_id = ? "
            "GROUP BY kind ORDER BY 2 DESC",
            sid,
        )
        if sid is not None
        else []
    )
    return {
        "layers": layers,
        "ratchet": _ratchet(con, sid) if sid is not None else [],
        "decisions": [{"kind": k, "count": c, "outcomes": o} for k, c, o in kinds],
    }


def _ratchet(con: sqlite3.Connection, sid: int) -> list[dict[str, Any]]:
    source = _rows(con, "SELECT source FROM snapshots WHERE id = ?", sid)[0][0]
    prev = _rows(
        con,
        "SELECT id FROM snapshots WHERE source = ? AND id < ? ORDER BY id DESC LIMIT 1",
        source,
        sid,
    )
    now = _counts(con, sid)
    before = _counts(con, prev[0][0]) if prev else None
    return [
        {"metric": k, "now": v, "before": before[k] if before else None} for k, v in now.items()
    ]


def dependencies(con: sqlite3.Connection, sid: int) -> dict[str, Any]:
    marks = ",".join("?" * len(_CONTAINERS))
    objs = _rows(
        con,
        f"SELECT uuid, type, name FROM objects WHERE snapshot_id = ? AND type NOT IN "
        f"({marks}) ORDER BY type, name",
        sid,
        *_CONTAINERS,
    )
    idx = {u: i for i, (u, _, _) in enumerate(objs)}
    ext: dict[str, int] = {}
    edges: set[tuple[int, int]] = set()
    for src, target, resolved in _rows(
        con,
        "SELECT source_uuid, target, resolved FROM refs WHERE snapshot_id = ? "
        "AND kind NOT IN ('platform','self')",
        sid,
    ):
        if src not in idx:
            continue
        if target in idx:
            edges.add((idx[src], idx[target]))
        elif resolved == 0:
            edges.add((idx[src], -1 - ext.setdefault(target, len(ext))))
    return {
        "objects": [[u, t, n] for u, t, n in objs],
        "ext": [e for e in ext],
        "edges": [list(e) for e in sorted(edges) if e[0] != e[1]],
    }


def processes(con: sqlite3.Connection, sid: int) -> list[dict[str, Any]]:
    return [
        {"uuid": u, "name": n, "nodes": nodes, "gateways": gw, "paths": paths}
        for u, n, nodes, gw, paths in _rows(
            con,
            "SELECT o.uuid, o.name, "
            "(SELECT COUNT(*) FROM nodes n WHERE n.snapshot_id = o.snapshot_id "
            "AND n.pm_uuid = o.uuid), "
            "(SELECT COUNT(*) FROM flows f WHERE f.snapshot_id = o.snapshot_id "
            "AND f.pm_uuid = o.uuid AND f.kind = 'gateway_rule'), "
            "(SELECT COALESCE(SUM(feasible),0) FROM path_stats s "
            "WHERE s.snapshot_id = o.snapshot_id "
            "AND s.pm_uuid = o.uuid) FROM objects o "
            "WHERE o.snapshot_id = ? AND o.type = 'processModel' ORDER BY o.name",
            sid,
        )
    ]


def process(con: sqlite3.Connection, sid: int, pm_uuid: str) -> dict[str, Any]:
    kinds = {"connection": 0, "gateway_rule": 1, "gateway_default": 2}
    return {
        "nodes": [
            [gui, type_id, lab]
            for gui, type_id, lab in _rows(
                con,
                "SELECT gui_id, type_id, COALESCE(NULLIF(label,''), type_name) FROM nodes "
                "WHERE snapshot_id = ? AND pm_uuid = ?",
                sid,
                pm_uuid,
            )
        ],
        "flows": [
            [a, b, kinds[k], lab, cond]
            for a, b, k, lab, cond in _rows(
                con,
                "SELECT from_gui, to_gui, kind, label, condition FROM flows "
                "WHERE snapshot_id = ? AND pm_uuid = ?",
                sid,
                pm_uuid,
            )
        ],
    }
