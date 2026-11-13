"""Layer 2: parse every SAIL source in a snapshot and store its decision points."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from atg.sail.ast import SailSyntaxError, parse
from atg.sail.branches import find
from atg.sail.printer import normalise, to_text

# (done, total) after each source.
SourceProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class Source:
    owner: str
    location: str  # "definition" or "gateway <from>-><to>"
    text: str


def sources(con: sqlite3.Connection, sid: int) -> list[Source]:
    """Rule, interface and decision definitions, plus every process gateway condition."""
    rows = con.execute(
        "SELECT owner_uuid, location, text FROM expressions WHERE snapshot_id = ? "
        "UNION ALL SELECT pm_uuid, 'gateway ' || from_gui || '->' || to_gui, condition "
        "FROM flows WHERE snapshot_id = ? AND kind = 'gateway_rule' AND condition != '' "
        "ORDER BY 1, 2",
        (sid, sid),
    ).fetchall()
    return [Source(*r) for r in rows]


def run(con: sqlite3.Connection, sid: int, on_source: SourceProgress | None = None) -> None:
    todo = sources(con, sid)
    parsed, branches = [], []
    for done, src in enumerate(todo, 1):
        if on_source is not None:
            on_source(done, len(todo))
        try:
            expr = parse(src.text)
        except SailSyntaxError as e:
            parsed.append((sid, src.owner, src.location, 0, 0, str(e), 0))
            continue
        found = find(expr)
        round_trip = to_text(expr) == normalise(src.text)
        parsed.append((sid, src.owner, src.location, 1, int(round_trip), "", len(found)))
        branches += [
            (
                sid,
                src.owner,
                src.location,
                b.kind,
                b.function,
                b.condition,
                b.outcomes,
                json.dumps(b.literals),
            )
            for b in found
        ]
    with con:
        con.executemany("INSERT INTO sail_parse VALUES (?,?,?,?,?,?,?)", parsed)
        con.executemany("INSERT INTO branches VALUES (?,?,?,?,?,?,?,?)", branches)
