"""Read helpers over the map (the SQLite store): names, details, settings, SAIL definitions.

Every module that reads the map for display or test generation goes through these, so the
queries live in one place. Writing the map is store.py; the layers fill it.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from atg.sail.display import Names


def names(con: sqlite3.Connection, sid: int) -> Names:
    objects = {
        u: (t, n)
        for u, t, n in con.execute(
            "SELECT uuid, type, name FROM objects WHERE snapshot_id = ?", (sid,)
        )
    }
    fields: dict[str, str] = {}
    for (d,) in con.execute(
        "SELECT d.details FROM object_details d JOIN objects o ON o.uuid = d.uuid "
        "AND o.snapshot_id = d.snapshot_id WHERE d.snapshot_id = ? AND o.type = 'recordType'",
        (sid,),
    ):
        fields.update({f["uuid"]: f["name"] for f in json.loads(d).get("fields", [])})
    return Names(objects, fields)


def details(con: sqlite3.Connection, sid: int, uuid: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT details FROM object_details WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
    ).fetchone()
    return json.loads(row[0]) if row else {}


def settings_by_type(
    con: sqlite3.Connection, sid: int, kind: str
) -> dict[str, list[dict[str, str]]]:
    return {
        u: json.loads(d).get("settings", [])
        for u, d in con.execute(
            "SELECT o.uuid, d.details FROM objects o JOIN object_details d "
            "ON d.snapshot_id = o.snapshot_id AND d.uuid = o.uuid "
            "WHERE o.snapshot_id = ? AND o.type = ?",
            (sid, kind),
        )
    }


def interface_definitions(con: sqlite3.Connection, sid: int) -> dict[str, str]:
    return dict(
        con.execute(
            "SELECT e.owner_uuid, e.text FROM expressions e JOIN objects o "
            "ON o.snapshot_id = e.snapshot_id AND o.uuid = e.owner_uuid "
            "WHERE e.snapshot_id = ? AND o.type = 'interface' AND e.location = 'definition'",
            (sid,),
        )
    )


def assignee_name(assignee: str, objects: dict[str, tuple[str, str]]) -> str:
    kind, name = objects.get(assignee, ("", ""))
    if kind == "group":
        return name
    if assignee.startswith("="):
        return f"expression {assignee}"
    return "group outside this export" if assignee.startswith("_e-") else assignee
