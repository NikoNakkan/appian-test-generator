"""Layer 4 views: the proposed features, their size, members and approval status."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any


def feature(con: sqlite3.Connection, sid: int, key: str) -> dict[str, Any]:
    share = Counter(
        u for (u,) in con.execute("SELECT uuid FROM feature_members WHERE snapshot_id = ?", (sid,))
    )
    rows = con.execute(
        "SELECT o.uuid, o.type, o.name FROM feature_members m JOIN objects o "
        "ON o.uuid = m.uuid AND o.snapshot_id = m.snapshot_id "
        "WHERE m.snapshot_id = ? AND m.key = ? ORDER BY o.type, o.name",
        (sid, key),
    ).fetchall()
    return {
        "members": [
            {"uuid": u, "type": t, "name": n, "shared_with": share[u] - 1} for u, t, n in rows
        ]
    }


def outside(con: sqlite3.Connection, sid: int) -> list[dict[str, str]]:
    return [
        {"kind": k, "name": n}
        for k, n in con.execute(
            "SELECT kind, name FROM outside_entries WHERE snapshot_id = ?", (sid,)
        )
    ]
