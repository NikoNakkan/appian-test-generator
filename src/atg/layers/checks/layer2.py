"""Layer 2 checks: every SAIL source parses, prints back identically, and the decision points
found match plain text counts of the raw source. Each check can fail."""

from __future__ import annotations

import re
import sqlite3

from atg.layers.checks.layer1 import CheckResult
from atg.layers.layer2_sail import sources

# Raw-text patterns, independent of the grammar. Strings and comments are blanked first;
# #"..." references are kept, since built-in functions are written that way.
_STRINGS = re.compile(r'#"[^"]*"|"(?:[^"]|"")*"|/\*[\s\S]*?\*/')


def _blank(text: str) -> str:
    return _STRINGS.sub(lambda m: m.group(0) if m.group(0).startswith("#") else '""', text)


_IF = re.compile(r'(?<![\w!.#"\'])if\s*\(')
_FOREACH = re.compile(r'#"SYSTEM_SYSRULES_forEach"\s*\(|(?<![\w!])a!forEach\s*\(')


def run(con: sqlite3.Connection, sid: int) -> list[CheckResult]:
    raw = [_blank(s.text) for s in sources(con, sid)]

    def one(sql: str) -> int:
        row = con.execute(sql, (sid,)).fetchone()
        return int(row[0] or 0)

    failed = con.execute(
        "SELECT o.name, p.location, p.error FROM sail_parse p LEFT JOIN objects o "
        "ON o.snapshot_id = p.snapshot_id AND o.uuid = p.owner_uuid "
        "WHERE p.snapshot_id = ? AND p.ok = 0 LIMIT 20",
        (sid,),
    ).fetchall()
    mismatched = con.execute(
        "SELECT o.name, p.location FROM sail_parse p LEFT JOIN objects o "
        "ON o.snapshot_id = p.snapshot_id AND o.uuid = p.owner_uuid "
        "WHERE p.snapshot_id = ? AND p.ok = 1 AND p.round_trip = 0 LIMIT 20",
        (sid,),
    ).fetchall()
    parsed = one("SELECT COUNT(*) FROM sail_parse WHERE snapshot_id = ? AND ok = 1")
    return [
        CheckResult(
            "SAIL sources parsed",
            len(raw),
            parsed,
            [f"{n or 'unknown object'} [{loc}]: {err}" for n, loc, err in failed],
        ),
        CheckResult(
            "round-trip identical",
            parsed,
            one("SELECT COUNT(*) FROM sail_parse WHERE snapshot_id = ? AND round_trip = 1"),
            [f"{n} [{loc}]" for n, loc in mismatched],
        ),
        CheckResult(
            "if() decisions found",
            sum(len(_IF.findall(t)) for t in raw),
            one("SELECT COUNT(*) FROM branches WHERE snapshot_id = ? AND kind = 'if'"),
        ),
        CheckResult(
            "forEach loops found",
            sum(len(_FOREACH.findall(t)) for t in raw),
            one("SELECT COUNT(*) FROM branches WHERE snapshot_id = ? AND function = 'a!forEach'"),
        ),
    ]
