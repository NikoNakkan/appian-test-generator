"""Regression impact between two snapshots of the same app.

1. What changed: objects added / removed / changed (content hash, version stamps ignored), and
   inside processes, which nodes changed (settings, form, outputs, outgoing flows).
2. What is affected: everything that uses a changed or removed object, transitively, with the
   chain of references that explains why.
Test verdicts built on this live in verdicts.py.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from atg.read.xmlutil import UUID_RE

_CONTAINERS = (
    "application",
    "folder",
    "rulesFolder",
    "processModelFolder",
    "knowledgeCenter",
    "document",
    "site",
)
_IGNORED_REFS = ("platform", "self")


@dataclass
class Impact:
    uuid: str
    type: str
    name: str
    status: str  # changed, added, removed, affected
    via: list[str] = field(default_factory=list)  # names, from this object to the change


def base_for(con: sqlite3.Connection, sid: int) -> int | None:
    """The previous snapshot of the same application (matched by the application object's UUID)."""
    apps = {
        u
        for (u,) in con.execute(
            "SELECT uuid FROM objects WHERE snapshot_id = ? AND type = 'application'", (sid,)
        )
    }
    for (other,) in con.execute("SELECT id FROM snapshots WHERE id < ? ORDER BY id DESC", (sid,)):
        theirs = {
            u
            for (u,) in con.execute(
                "SELECT uuid FROM objects WHERE snapshot_id = ? AND type = 'application'", (other,)
            )
        }
        if apps & theirs:
            return int(other)
    return None


def objects_of(con: sqlite3.Connection, sid: int) -> dict[str, tuple[str, str, str]]:
    return {
        u: (t, n, h)
        for u, t, n, h in con.execute(
            "SELECT uuid, type, name, content_hash FROM objects WHERE snapshot_id = ?", (sid,)
        )
    }


def _users_of(con: sqlite3.Connection, sid: int) -> dict[str, set[str]]:
    """target -> objects whose behaviour depends on it.

    Not every reference is a dependency. Containers only list things. A record type points at
    its own views and action processes, but its data does not change when they do. And whatever
    starts a process does not depend on what happens inside it (sub-processes are tested on
    their own, the caller only checks the call), so references to process models are not
    followed either. A changed process still flags its own paths, node by node.
    """
    types = dict(con.execute("SELECT uuid, type FROM objects WHERE snapshot_id = ?", (sid,)))
    users: dict[str, set[str]] = {}
    for src, target in con.execute(
        "SELECT DISTINCT source_uuid, target FROM refs WHERE snapshot_id = ? "
        "AND kind NOT IN (?, ?)",
        (sid, *_IGNORED_REFS),
    ):
        kind = types.get(src)
        if src == target or kind in _CONTAINERS or kind == "recordType":
            continue
        if types.get(target) == "processModel":
            continue
        users.setdefault(target, set()).add(src)
    return users


def impacts(con: sqlite3.Connection, base: int, head: int) -> dict[str, Impact]:
    old, new = objects_of(con, base), objects_of(con, head)
    out: dict[str, Impact] = {}
    for u, (t, n, h) in new.items():
        if u not in old:
            out[u] = Impact(u, t, n, "added")
        elif old[u][2] != h:
            out[u] = Impact(u, t, n, "changed")
    for u, (t, n, _) in old.items():
        if u not in new:
            out[u] = Impact(u, t, n, "removed")
    roots = [u for u, i in out.items() if i.status in ("changed", "removed")]
    users = _users_of(con, head)
    for u, s in _users_of(con, base).items():  # who used a removed object
        if u in out and out[u].status == "removed":
            users.setdefault(u, set()).update(x for x in s if x in new)
    queue = deque(roots)
    while queue:
        u = queue.popleft()
        for user in sorted(users.get(u, ())):
            if user in out or user not in new:
                continue
            t, n, _ = new[user]
            out[user] = Impact(user, t, n, "affected", [out[u].name, *out[u].via][:6])
            queue.append(user)
    return out


def node_fingerprints(
    con: sqlite3.Connection, sid: int, pm: str
) -> dict[int, tuple[str, set[str]]]:
    """guiId -> (hash of everything the node is, UUIDs the node refers to)."""
    flows: dict[int, list[Any]] = {}
    for a, b, k, lab, cond in con.execute(
        "SELECT from_gui, to_gui, kind, label, condition FROM flows WHERE snapshot_id = ? "
        "AND pm_uuid = ? ORDER BY rowid",
        (sid, pm),
    ):
        flows.setdefault(a, []).append([b, k, lab, cond])
    details = dict(
        con.execute(
            "SELECT gui_id, details FROM node_details WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    )
    out = {}
    for gui, type_id, label, calls in con.execute(
        "SELECT gui_id, type_id, label, calls FROM nodes WHERE snapshot_id = ? AND pm_uuid = ?",
        (sid, pm),
    ):
        body = json.dumps([type_id, label, details.get(gui, ""), flows.get(gui, [])])
        refs = set(UUID_RE.findall(body)) | ({calls} if calls else set())
        out[gui] = (hashlib.sha1(body.encode("utf-8")).hexdigest(), refs)
    return out
