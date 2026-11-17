"""SQLite map. Every row belongs to a snapshot (one per ingested export)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from atg.model import RefKind, Snapshot
from atg.read.link import resolvable_targets

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY, source TEXT, appian_version TEXT, reader TEXT, created_at TEXT,
  max_paths INTEGER);
CREATE TABLE IF NOT EXISTS objects (
  snapshot_id INTEGER, uuid TEXT, type TEXT, name TEXT, path TEXT, haul_root TEXT,
  content_hash TEXT, PRIMARY KEY (snapshot_id, uuid));
CREATE TABLE IF NOT EXISTS internal_ids (
  snapshot_id INTEGER, owner_uuid TEXT, internal_id TEXT);
CREATE TABLE IF NOT EXISTS refs (
  snapshot_id INTEGER, source_uuid TEXT, kind TEXT, target TEXT, context TEXT,
  occurrences INTEGER, resolved INTEGER);
CREATE TABLE IF NOT EXISTS uuid_uses (
  snapshot_id INTEGER, path TEXT, token TEXT, use TEXT, occurrences INTEGER);
CREATE TABLE IF NOT EXISTS nodes (
  snapshot_id INTEGER, pm_uuid TEXT, gui_id INTEGER, node_uuid TEXT, type_id TEXT,
  type_name TEXT, label TEXT, writes TEXT, calls TEXT, assignees TEXT);
CREATE TABLE IF NOT EXISTS flows (
  snapshot_id INTEGER, pm_uuid TEXT, from_gui INTEGER, to_gui INTEGER, kind TEXT,
  label TEXT, condition TEXT);
CREATE TABLE IF NOT EXISTS unknowns (snapshot_id INTEGER, kind TEXT, value TEXT, path TEXT);
CREATE TABLE IF NOT EXISTS binary_files (snapshot_id INTEGER, path TEXT);
CREATE TABLE IF NOT EXISTS check_results (
  snapshot_id INTEGER, layer INTEGER, name TEXT, expected INTEGER, actual INTEGER, ok INTEGER,
  details TEXT);
CREATE TABLE IF NOT EXISTS expressions (
  snapshot_id INTEGER, owner_uuid TEXT, location TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS sail_parse (
  snapshot_id INTEGER, owner_uuid TEXT, location TEXT, ok INTEGER, round_trip INTEGER,
  error TEXT, branch_count INTEGER);
CREATE TABLE IF NOT EXISTS branches (
  snapshot_id INTEGER, owner_uuid TEXT, location TEXT, kind TEXT, function TEXT, condition TEXT,
  outcomes INTEGER, literals TEXT);
CREATE TABLE IF NOT EXISTS paths (
  snapshot_id INTEGER, pm_uuid TEXT, path_no INTEGER, steps TEXT, decisions TEXT, calls TEXT,
  tasks TEXT, loops INTEGER, choices TEXT);
CREATE TABLE IF NOT EXISTS path_stats (
  snapshot_id INTEGER, pm_uuid TEXT, feasible INTEGER, infeasible INTEGER, truncated INTEGER,
  loops INTEGER);
CREATE TABLE IF NOT EXISTS entry_points (
  snapshot_id INTEGER, owner_uuid TEXT, kind TEXT, name TEXT, target TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS features (
  snapshot_id INTEGER, key TEXT, name TEXT, entries TEXT);
CREATE TABLE IF NOT EXISTS feature_members (snapshot_id INTEGER, key TEXT, uuid TEXT);
CREATE TABLE IF NOT EXISTS outside_entries (
  snapshot_id INTEGER, kind TEXT, name TEXT, target TEXT);
CREATE TABLE IF NOT EXISTS feature_approvals (
  key TEXT PRIMARY KEY, decision TEXT, name TEXT, approver TEXT, approved_on TEXT,
  row_hash TEXT);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY, snapshot_id INTEGER, user TEXT, object TEXT, result TEXT, note TEXT,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS object_details (snapshot_id INTEGER, uuid TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS node_details (
  snapshot_id INTEGER, pm_uuid TEXT, gui_id INTEGER, details TEXT);
CREATE INDEX IF NOT EXISTS object_details_uuid ON object_details (snapshot_id, uuid);
CREATE INDEX IF NOT EXISTS paths_pm ON paths (snapshot_id, pm_uuid);
CREATE INDEX IF NOT EXISTS refs_target ON refs (snapshot_id, target);
CREATE INDEX IF NOT EXISTS refs_source ON refs (snapshot_id, source_uuid);
CREATE INDEX IF NOT EXISTS nodes_pm ON nodes (snapshot_id, pm_uuid);
CREATE INDEX IF NOT EXISTS node_details_pm ON node_details (snapshot_id, pm_uuid, gui_id);
CREATE INDEX IF NOT EXISTS flows_pm ON flows (snapshot_id, pm_uuid);
CREATE INDEX IF NOT EXISTS path_stats_pm ON path_stats (snapshot_id, pm_uuid);
CREATE INDEX IF NOT EXISTS expressions_owner ON expressions (snapshot_id, owner_uuid);
CREATE INDEX IF NOT EXISTS sail_parse_owner ON sail_parse (snapshot_id, owner_uuid);
CREATE INDEX IF NOT EXISTS branches_owner ON branches (snapshot_id, owner_uuid);
CREATE INDEX IF NOT EXISTS entry_points_owner ON entry_points (snapshot_id, owner_uuid);
CREATE INDEX IF NOT EXISTS feature_members_key ON feature_members (snapshot_id, key);
"""

_NEVER_RESOLVED = {RefKind.PLATFORM, RefKind.SELF}


# Columns added after a table first shipped: (table, column, type). Old maps get them on connect.
_ADDED_COLUMNS = [
    ("nodes", "writes", "TEXT"),
    ("nodes", "calls", "TEXT"),
    ("nodes", "assignees", "TEXT"),
    ("findings", "claim", "TEXT"),
    ("findings", "environment", "TEXT"),
    ("paths", "choices", "TEXT"),
    ("snapshots", "max_paths", "INTEGER"),
]


def connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    for table, column, kind in _ADDED_COLUMNS:
        have = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
    return con


def save(con: sqlite3.Connection, snap: Snapshot) -> int:
    with con:
        cur = con.execute(
            "INSERT INTO snapshots (source, appian_version, reader, created_at) VALUES (?,?,?,?)",
            (snap.source, snap.appian_version, snap.reader, datetime.now(UTC).isoformat()),
        )
        sid = cur.lastrowid
        assert sid is not None
        _save_objects(con, sid, snap)
        con.executemany(
            "INSERT INTO unknowns VALUES (?,?,?,?)",
            [(sid, u.kind.value, u.value, u.path) for u in snap.unknowns],
        )
        con.executemany(
            "INSERT INTO binary_files VALUES (?,?)", [(sid, p) for p in snap.binary_files]
        )
    return sid


def _save_objects(con: sqlite3.Connection, sid: int, snap: Snapshot) -> None:
    targets = resolvable_targets(snap.objects)
    names = {o.name for o in snap.objects}
    for o in snap.objects:
        con.execute(
            "INSERT INTO objects VALUES (?,?,?,?,?,?,?)",
            (sid, o.uuid, o.type, o.name, o.path, o.haul_root, o.content_hash),
        )
        con.executemany(
            "INSERT INTO internal_ids VALUES (?,?,?)", [(sid, o.uuid, i) for i in o.internal_ids]
        )
        con.executemany(
            "INSERT INTO entry_points VALUES (?,?,?,?,?,?)",
            [(sid, o.uuid, e.kind, e.name, e.target, e.description) for e in o.entry_points],
        )
        con.execute(
            "INSERT INTO object_details VALUES (?,?,?)", (sid, o.uuid, json.dumps(o.details))
        )
        con.executemany(
            "INSERT INTO node_details VALUES (?,?,?,?)",
            [(sid, o.uuid, gui, json.dumps(d)) for gui, d in o.node_details.items()],
        )
        if o.definition:
            con.execute(
                "INSERT INTO expressions VALUES (?,?,?,?)",
                (sid, o.uuid, "definition", o.definition),
            )
        refs = Counter((r.kind, r.target, r.context) for r in o.references)
        con.executemany(
            "INSERT INTO refs VALUES (?,?,?,?,?,?,?)",
            [
                (sid, o.uuid, kind.value, target, ctx, n, _resolved(kind, target, targets, names))
                for (kind, target, ctx), n in refs.items()
            ],
        )
        # Totals per file and kind of use: all the UUID sweep check needs. The token column is
        # left empty (maps imported before kept one row per token).
        uses = Counter(t.use for t in o.tokens)
        con.executemany(
            "INSERT INTO uuid_uses VALUES (?,?,?,?,?)",
            [(sid, o.path, None, use.value, n) for use, n in uses.items()],
        )
        con.executemany(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    sid,
                    o.uuid,
                    n.gui_id,
                    n.node_uuid,
                    n.type_id,
                    n.type_name,
                    n.label,
                    json.dumps(n.writes),
                    n.calls,
                    json.dumps(n.assignees),
                )
                for n in o.nodes
            ],
        )
        con.executemany(
            "INSERT INTO flows VALUES (?,?,?,?,?,?,?)",
            [
                (sid, o.uuid, f.from_gui, f.to_gui, f.kind.value, f.label, f.condition)
                for f in o.flows
            ],
        )


def _resolved(kind: RefKind, target: str, targets: set[str], names: set[str]) -> int | None:
    if kind in _NEVER_RESOLVED:
        return None
    if kind is RefKind.SAIL_NAME:
        return int(target in names)
    return int(target in targets)
