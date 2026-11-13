"""Layer 4: build the proposed features for a snapshot and store them."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from atg.layers.feature_engine import build


def run(con: sqlite3.Connection, sid: int) -> None:
    features, outside = build(con, sid)
    with con:
        con.executemany(
            "INSERT INTO features VALUES (?,?,?,?)",
            [(sid, f.key, f.name, json.dumps([asdict(e) for e in f.entries])) for f in features],
        )
        con.executemany(
            "INSERT INTO feature_members VALUES (?,?,?)",
            [(sid, f.key, m) for f in features for m in sorted(f.members)],
        )
        con.executemany(
            "INSERT INTO outside_entries VALUES (?,?,?,?)",
            [(sid, e.kind, e.name, e.target) for e in outside],
        )
