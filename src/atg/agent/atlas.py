"""The map loaded once for the agent: objects, links both ways, constants resolved to groups."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from atg import mapdb
from atg.read.xmlutil import UUID_RE
from atg.sail.display import Names

_SKIP_KINDS = ("platform", "self")


@dataclass
class Atlas:
    con: sqlite3.Connection
    sid: int
    objects: dict[str, tuple[str, str]]
    uses: dict[str, list[str]]
    used_by: dict[str, list[str]]
    outside: dict[str, int]  # object -> references that point outside this export
    names: Names
    _details: dict[str, dict[str, Any]] = field(default_factory=dict)
    _text: dict[str, str] | None = None
    memo: dict[str, Any] = field(default_factory=dict)  # results built once per load

    def name(self, uuid: str) -> str:
        return self.objects.get(uuid, ("", uuid))[1]

    def type(self, uuid: str) -> str:
        return self.objects.get(uuid, ("", ""))[0]

    def det(self, uuid: str) -> dict[str, Any]:
        if uuid not in self._details:
            self._details[uuid] = mapdb.details(self.con, self.sid, uuid)
        return self._details[uuid]

    def text(self, uuid: str) -> str:
        """The SAIL of a rule, interface or decision ("" for anything else)."""
        if self._text is None:
            self._text = dict(
                self.con.execute(
                    "SELECT owner_uuid, text FROM expressions WHERE snapshot_id = ? "
                    "AND location = 'definition'",
                    (self.sid,),
                )
            )
        return self._text.get(uuid, "")

    def resolve(self, token: str) -> list[str]:
        """A constant stands for the UUIDs it holds; anything else stands for itself."""
        if self.type(token) != "constant":
            return [token]
        values = self.det(token).get("constant", {}).get("values", [])
        return [u for v in values for u in UUID_RE.findall(str(v))] or [token]

    def ref(self, uuid: str) -> dict[str, str]:
        return {"id": uuid, "type": self.type(uuid) or "outside", "name": self.name(uuid)}


def load(con: sqlite3.Connection, sid: int) -> Atlas:
    objects = {
        u: (t, n)
        for u, t, n in con.execute(
            "SELECT uuid, type, name FROM objects WHERE snapshot_id = ?", (sid,)
        )
    }
    uses: dict[str, list[str]] = {}
    used_by: dict[str, list[str]] = {}
    outside: dict[str, int] = {}
    for src, target, resolved, n in con.execute(
        "SELECT source_uuid, target, resolved, occurrences FROM refs WHERE snapshot_id = ? "
        f"AND kind NOT IN {_SKIP_KINDS}",
        (sid,),
    ):
        if target in objects and src != target:
            if target not in uses.setdefault(src, []):
                uses[src].append(target)
            if src not in used_by.setdefault(target, []):
                used_by[target].append(src)
        elif resolved == 0:
            outside[src] = outside.get(src, 0) + n
    return Atlas(con, sid, objects, uses, used_by, outside, mapdb.names(con, sid))


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
