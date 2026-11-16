"""The analysis file: separate from the map, one per map file, every row tied to a snapshot."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atg.agent.atlas import Atlas

PROMPT_VERSION = "1"
# Starting values borrowed from code-agent research (SWE-agent, RepoGraph, AutoCodeRover);
# not validated on Appian exports. Recorded in every idempotency key.
PARAMS = {"view_cap": 100, "list_cap": 50, "hops": 1, "rounds": 10, "dry_streak": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  snapshot_id INTEGER, id TEXT, kind TEXT, subject TEXT, key TEXT, status TEXT, priority INTEGER,
  lease_until TEXT, attempts INTEGER DEFAULT 0, note TEXT, updated_at TEXT,
  PRIMARY KEY (snapshot_id, id));
CREATE TABLE IF NOT EXISTS reads (
  snapshot_id INTEGER, item_id TEXT, object TEXT, content_hash TEXT, part TEXT,
  truncated INTEGER, total INTEGER, resolved INTEGER, at TEXT);
CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY, snapshot_id INTEGER, item_id TEXT, key TEXT, subject TEXT,
  predicate TEXT, value TEXT, level TEXT, evidence TEXT, input_hash TEXT, model TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY, snapshot_id INTEGER, item_id TEXT, subject TEXT, text TEXT,
  status TEXT, answer TEXT, answered_by TEXT, asked_at TEXT, answered_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY, snapshot_id INTEGER, kind TEXT, target TEXT, payload TEXT, by TEXT,
  reason TEXT, input_hash TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS authorisations (
  id INTEGER PRIMARY KEY, environment TEXT, scope TEXT, mode TEXT, by TEXT, granted_at TEXT,
  expires_at TEXT);
CREATE INDEX IF NOT EXISTS items_status ON items (snapshot_id, status);
CREATE INDEX IF NOT EXISTS claims_subject ON claims (snapshot_id, subject);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def digest(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def path_for(map_con: sqlite3.Connection) -> Path:
    main = next(row[2] for row in map_con.execute("PRAGMA database_list") if row[1] == "main")
    if not main:
        raise ValueError("the map must be a file to keep its analysis next to it")
    p = Path(main)
    return p.with_name(p.stem + ".analysis.db")


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def open_for(atlas: Atlas) -> sqlite3.Connection:
    """The analysis connection for this map, opened once per Atlas."""
    if "analysis" not in atlas.memo:
        atlas.memo["analysis"] = connect(path_for(atlas.con))
    con: sqlite3.Connection = atlas.memo["analysis"]
    return con


def content_hash(atlas: Atlas, uuid: str) -> str:
    if "hashes" not in atlas.memo:
        atlas.memo["hashes"] = dict(
            atlas.con.execute(
                "SELECT uuid, content_hash FROM objects WHERE snapshot_id = ?", (atlas.sid,)
            )
        )
    found: str = atlas.memo["hashes"].get(uuid, "")
    return found


def idempotency_key(kind: str, subject: str, input_hash: str) -> str:
    return digest(kind, subject, input_hash, PROMPT_VERSION, PARAMS)
