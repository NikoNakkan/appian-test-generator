"""Sentences shared by UAT scenarios: how a test starts, the rows it needs, what to fill in."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from atg.testgen import urls


def rows_needed(records: list[dict[str, Any]], verb: str = "has matching rows in") -> list[str]:
    """One line per record type: where its rows go and what else they need."""
    out = []
    for r in records:
        where = f" (table {r['table']})" if r.get("source") == "RDBMS_TABLE" and r["table"] else ""
        if r.get("source") == "EXPRESSION":
            where = " (comes from an expression or API: needs a fake)"
        line = f"The test database {verb} {r['name']}{where}"
        if r.get("related"):
            rel = ", ".join(
                f"{x['name']} ({x['kind'].replace('_', ' ').lower()})" for x in r["related"]
            )
            line += f", with their related {rel}"
        if r.get("sync", {}).get("frequency"):
            line += "; it is a synced record, so sync it after inserting rows"
        if r.get("computed"):
            line += f"; {', '.join(r['computed'])} are calculated by Appian, do not set them"
        out.append(line + ".")
    return out


def how_started(con: sqlite3.Connection, sid: int, pm: str) -> str:
    owners = dict(con.execute("SELECT uuid, name FROM objects WHERE snapshot_id = ?", (sid,)))
    for kind, name, owner in con.execute(
        "SELECT kind, name, owner_uuid FROM entry_points WHERE snapshot_id = ? AND target = ?",
        (sid, pm),
    ):
        where = owners.get(owner, "the app")
        at = f" ({url})" if (url := urls.record_lists(con, sid).get(owner)) else ""
        if kind == "related action":
            return f"Open a {where} record from its list{at} and run its related action “{name}”."
        if kind == "record list action":
            return f"Open the {where} list{at} and click “{name}”."
        return f"Open “{name}” ({kind} of {where})."
    parents = sorted(
        {
            owners.get(p, p)
            for p, calls in con.execute(
                "SELECT DISTINCT pm_uuid, calls FROM paths WHERE snapshot_id = ?", (sid,)
            )
            if pm in json.loads(calls)
        }
    )
    if parents:
        return f"Run {', '.join(parents[:2])} up to the point where it starts this process."
    return "Start the process directly (nothing in this export starts it)."


def fills_text(pairs: list[tuple[str, list[str]]]) -> str:
    """'claim: “Title” (text box), “Amount” (number box); submitted' for a step."""
    return "; ".join(f"{name}: {', '.join(places)}" if places else name for name, places in pairs)
