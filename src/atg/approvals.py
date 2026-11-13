"""Feature approval through Excel: export a sheet, a person fills it in, import it back.

Strict on the way back in: each row carries a hash of what was shown, so a row about a
feature that changed since export is refused; the decision must be one of the dropdown
values; blank is never approval; "edit" needs the new name; every decision needs a name.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

DECISIONS = ("approved", "edit", "rejected")
HEADERS = [
    "Feature",
    "Original name",
    "Starts from",
    "Processes",
    "Screens",
    "Rules",
    "Decision",
    "New name (for edit)",
    "Your name",
    "id",
    "check",
]


def row_hash(con: sqlite3.Connection, sid: int, key: str) -> str:
    name_row = con.execute(
        "SELECT name FROM features WHERE snapshot_id = ? AND key = ?", (sid, key)
    ).fetchone()
    members = sorted(
        m
        for (m,) in con.execute(
            "SELECT uuid FROM feature_members WHERE snapshot_id = ? AND key = ?", (sid, key)
        )
    )
    text = "|".join([key, name_row[0] if name_row else "", *members])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def approval_status(con: sqlite3.Connection, sid: int, key: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT decision, name, approver, approved_on, row_hash "
        "FROM feature_approvals WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return {"status": "waiting", "decision": None}
    decision, name, approver, on, stored_hash = row
    stale = stored_hash != row_hash(con, sid, key)
    return {
        "status": "needs re-approval" if stale else decision,
        "decision": decision,
        "name": name,
        "approver": approver,
        "on": on,
    }


def feature_list(con: sqlite3.Connection, sid: int) -> list[dict[str, Any]]:
    """Every proposed feature with its size and approval status (UI and Excel sheet)."""
    types = dict(con.execute("SELECT uuid, type FROM objects WHERE snapshot_id = ?", (sid,)))
    members: dict[str, list[str]] = {}
    for key, uuid in con.execute(
        "SELECT key, uuid FROM feature_members WHERE snapshot_id = ?", (sid,)
    ):
        members.setdefault(key, []).append(uuid)
    share = Counter(u for ms in members.values() for u in ms)
    paths = dict(
        con.execute("SELECT pm_uuid, feasible FROM path_stats WHERE snapshot_id = ?", (sid,))
    )
    decisions = Counter(
        o for (o,) in con.execute("SELECT owner_uuid FROM branches WHERE snapshot_id = ?", (sid,))
    )
    out = []
    for key, name, entries in con.execute(
        "SELECT key, name, entries FROM features WHERE snapshot_id = ? ORDER BY name", (sid,)
    ):
        ms = members.get(key, [])
        kinds = Counter(types.get(m) for m in ms)
        approval = approval_status(con, sid, key)
        shown = approval.get("name") if approval["status"] == "edit" else None
        out.append(
            {
                "key": key,
                "name": shown or name,
                "original_name": name,
                "entries": [{**e, "name": e["name"]} for e in json.loads(entries)],
                "processes": kinds["processModel"],
                "screens": kinds["interface"],
                "rules": kinds["rule"] + kinds["decision"],
                "paths": sum(paths.get(m, 0) for m in ms),
                "decisions": sum(decisions[m] for m in ms),
                "only_here": sum(1 for m in ms if share[m] == 1),
                "approval": approval,
            }
        )
    return out


def export_sheet(con: sqlite3.Connection, sid: int) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Features"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    pick = PatternFill("solid", fgColor="FFF4D6")
    for f in feature_list(con, sid):
        ws.append(
            [
                f["name"],
                f["original_name"],
                ", ".join(e["kind"] for e in f["entries"]),
                f["processes"],
                f["screens"],
                f["rules"],
                f["approval"]["decision"] or "",
                "",
                "",
                f["key"],
                row_hash(con, sid, f["key"]),
            ]
        )
        for col in (7, 8, 9):
            ws.cell(ws.max_row, col).fill = pick
    rule = DataValidation(
        type="list",
        formula1='"' + ",".join(DECISIONS) + '"',
        allow_blank=True,
        showErrorMessage=True,
        error="Pick approved, edit or rejected.",
    )
    ws.add_data_validation(rule)
    rule.add(f"G2:G{max(ws.max_row, 2)}")
    for letter, width in zip(
        "ABCDEFGHIJK", (40, 40, 28, 10, 9, 8, 12, 30, 18, 12, 18), strict=True
    ):
        ws.column_dimensions[letter].width = width
    ws.column_dimensions["J"].hidden = ws.column_dimensions["K"].hidden = True
    help_ws = wb.create_sheet("How to fill in")
    for line in (
        "Fill in the yellow columns only.",
        "Decision: approved (the feature is right), edit (right, but give it a better name in "
        "New name), rejected (not a real feature, e.g. a test process).",
        "Your name: who decided. Required for every decision.",
        "Leave Decision empty for features you have not looked at. Empty never counts as approved.",
        "Then upload this file in the tool (Features, Upload filled sheet).",
    ):
        help_ws.append([line])
    help_ws.column_dimensions["A"].width = 110
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@dataclass
class ImportResult:
    applied: int = 0
    skipped_blank: int = 0
    problems: list[str] = field(default_factory=list)


def import_sheet(con: sqlite3.Connection, sid: int, data: bytes) -> ImportResult:
    result = ImportResult()
    try:
        ws = load_workbook(io.BytesIO(data), data_only=True)["Features"]
    except Exception:  # not an xlsx, or the sheet was renamed
        result.problems.append("This isn't the approval sheet. Download it again and fill it in.")
        return result
    head = [str(c.value or "") for c in ws[1]]
    if head[: len(HEADERS)] != HEADERS:
        result.problems.append("The columns were changed. Download a fresh sheet.")
        return result
    rows = []
    for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        cells = ["" if v is None else str(v).strip() for v in row[: len(HEADERS)]]
        feature, decision, new_name, who, key, check = (
            cells[0],
            cells[6].lower(),
            cells[7],
            cells[8],
            cells[9],
            cells[10],
        )
        if not key:
            continue
        if not decision:
            result.skipped_blank += 1
            continue
        problem = _problem(con, sid, key, check, decision, new_name, who)
        if problem:
            result.problems.append(f"Row {n} ({feature}): {problem}")
            continue
        rows.append((key, decision, new_name if decision == "edit" else feature, who, check))
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with con:
        con.executemany(
            "INSERT OR REPLACE INTO feature_approvals VALUES (?,?,?,?,?,?)",
            [(k, d, nm, who, stamp, h) for k, d, nm, who, h in rows],
        )
    result.applied = len(rows)
    return result


def _problem(
    con: sqlite3.Connection, sid: int, key: str, check: str, decision: str, new_name: str, who: str
) -> str:
    if decision not in DECISIONS:
        return f"decision must be approved, edit or rejected, not {decision!r}"
    if decision == "edit" and not new_name:
        return "edit needs the new name in 'New name (for edit)'"
    if not who:
        return "add your name in 'Your name'"
    if check != row_hash(con, sid, key):
        return "this feature changed since the sheet was made; download a fresh sheet"
    return ""
