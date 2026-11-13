"""Layer 1 checks: raw counts vs the SQL map, UUID sweep, unknowns. Each can fail."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from atg.layers.checks.raw import RawCounts, count


@dataclass
class CheckResult:
    name: str
    expected: int
    actual: int
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.expected == self.actual and not self.details


def run(con: sqlite3.Connection, sid: int, root: Path) -> list[CheckResult]:
    raw = count(root)
    return [
        _files(con, sid, raw),
        *_roots(con, sid, raw),
        _simple(con, sid, "process nodes", raw.nodes, "SELECT COUNT(*) FROM nodes"),
        _flows(con, sid, "connections", raw.connections, "connection"),
        _flows(con, sid, "gateway rules", raw.gateway_rules, "gateway_rule"),
        _flows(con, sid, "gateway defaults", raw.gateway_defaults, "gateway_default"),
        _simple(
            con,
            sid,
            'canonical #" refs',
            raw.canonical_refs,
            "SELECT COALESCE(SUM(occurrences),0) FROM refs WHERE (context LIKE 'urn:%' "
            "OR kind IN ('sail','sail_name','platform','self'))",
        ),
        _sweep(con, sid, raw),
        _unknowns(con, sid),
    ]


def _one(con: sqlite3.Connection, sql: str, *args: object) -> int:
    row = con.execute(sql, args).fetchone()
    return int(row[0]) if row else 0


def _simple(con: sqlite3.Connection, sid: int, name: str, expected: int, sql: str) -> CheckResult:
    where = " AND" if " WHERE " in sql else " WHERE"
    return CheckResult(name, expected, _one(con, f"{sql}{where} snapshot_id = ?", sid))


def _flows(con: sqlite3.Connection, sid: int, name: str, expected: int, kind: str) -> CheckResult:
    sql = "SELECT COUNT(*) FROM flows WHERE snapshot_id = ? AND kind = ?"
    return CheckResult(name, expected, _one(con, sql, sid, kind))


def _files(con: sqlite3.Connection, sid: int, raw: RawCounts) -> CheckResult:
    objects = _one(con, "SELECT COUNT(*) FROM objects WHERE snapshot_id = ?", sid)
    unknown_files = _one(
        con,
        "SELECT COUNT(DISTINCT path) FROM unknowns WHERE snapshot_id = ? AND kind IN "
        "('parse_error','haul_root','content_subtype','no_uuid')",
        sid,
    )
    return CheckResult("data files -> object or unknown", raw.data_files, objects + unknown_files)


def _roots(con: sqlite3.Connection, sid: int, raw: RawCounts) -> list[CheckResult]:
    rows = dict(
        con.execute(
            "SELECT haul_root, COUNT(*) FROM objects WHERE snapshot_id = ? GROUP BY haul_root",
            (sid,),
        ).fetchall()
    )
    return [
        CheckResult(f"objects: {root}", n, int(rows.get(root, 0)))
        for root, n in sorted(raw.roots.items())
    ]


def _sweep(con: sqlite3.Connection, sid: int, raw: RawCounts) -> CheckResult:
    seen = dict(
        con.execute(
            "SELECT path, SUM(occurrences) FROM uuid_uses WHERE snapshot_id = ? GROUP BY path",
            (sid,),
        ).fetchall()
    )
    details = [
        f"{path}: raw {n}, classified {int(seen.get(path, 0))}"
        for path, n in sorted(raw.uuids_by_path.items())
        if n != int(seen.get(path, 0))
    ]
    total = sum(raw.uuids_by_path.values())
    return CheckResult(
        "UUID sweep (every token classified)", total, sum(map(int, seen.values())), details[:20]
    )


def _unknowns(con: sqlite3.Connection, sid: int) -> CheckResult:
    rows = con.execute(
        "SELECT kind, value, COUNT(*) FROM unknowns WHERE snapshot_id = ? "
        "GROUP BY kind, value ORDER BY 3 DESC",
        (sid,),
    ).fetchall()
    return CheckResult(
        "unknowns", 0, sum(r[2] for r in rows), [f"{k} {v!r} x{n}" for k, v, n in rows]
    )
