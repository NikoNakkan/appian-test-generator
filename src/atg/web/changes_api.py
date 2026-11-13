"""Changes view: what changed since an earlier snapshot, what it affects, which tests to run."""

from __future__ import annotations

import difflib
import json
import sqlite3
from typing import Any

from atg import mapdb
from atg.regression import impact, verdicts
from atg.sail.display import plain, to_designer


def changes(con: sqlite3.Connection, head: int, base: int | None) -> dict[str, Any]:
    base = base or impact.base_for(con, head)
    if base is None:
        return {
            "error": "There's no earlier import of this app to compare with. Import a newer "
            "version of the same export, then open this view on the newer snapshot."
        }
    r = verdicts.report(con, base, head)
    by_process: dict[str, dict[str, Any]] = {}
    other = []
    for v in r["verdicts"]:
        if v["kind"] != "path":
            other.append(v)
            continue
        p = by_process.setdefault(v["ref"], {"uuid": v["ref"], "name": v["owner"], "paths": []})
        p["paths"].append({"item": v["item"], "verdict": v["verdict"], "reasons": v["reasons"]})
    r["processes"] = sorted(by_process.values(), key=lambda p: -len(p["paths"]))
    r["rules"] = [v for v in other if v["kind"] == "rule"]
    r["features"] = [v for v in other if v["kind"] == "feature"]
    del r["verdicts"]
    return r


def object_diff(con: sqlite3.Connection, head: int, base: int, uuid: str) -> dict[str, Any]:
    """Line diffs of an object's code and settings, and of each changed process node."""
    parts = []
    for label, old, new in _texts(con, base, head, uuid):
        if old != new:
            lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2))
            parts.append({"label": label, "lines": lines[2:]})  # skip the ---/+++ header
    return {"parts": parts}


def _texts(con: sqlite3.Connection, base: int, head: int, uuid: str) -> list[tuple[str, str, str]]:
    def definition(sid: int) -> str:
        row = con.execute(
            "SELECT text FROM expressions WHERE snapshot_id = ? AND owner_uuid = ? "
            "AND location = 'definition'",
            (sid, uuid),
        ).fetchone()
        return plain(to_designer(row[0], mapdb.names(con, sid))) if row else ""

    def details(sid: int) -> str:
        row = con.execute(
            "SELECT details FROM object_details WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
        ).fetchone()
        return json.dumps(json.loads(row[0]), indent=1, ensure_ascii=False) if row else ""

    out = [("Code", definition(base), definition(head)), ("Settings", details(base), details(head))]
    old_nodes = impact.node_fingerprints(con, base, uuid)
    new_nodes = impact.node_fingerprints(con, head, uuid)
    for gui in sorted(set(old_nodes) | set(new_nodes)):
        if old_nodes.get(gui, ("",))[0] != new_nodes.get(gui, ("",))[0]:
            out.append(
                (
                    f"Node {gui}: {_label(con, head, uuid, gui) or _label(con, base, uuid, gui)}",
                    _node_text(con, base, uuid, gui),
                    _node_text(con, head, uuid, gui),
                )
            )
    return out


def _label(con: sqlite3.Connection, sid: int, pm: str, gui: int) -> str:
    row = con.execute(
        "SELECT COALESCE(NULLIF(label, ''), type_name) FROM nodes WHERE snapshot_id = ? "
        "AND pm_uuid = ? AND gui_id = ?",
        (sid, pm, gui),
    ).fetchone()
    return str(row[0]) if row else ""


def _node_text(con: sqlite3.Connection, sid: int, pm: str, gui: int) -> str:
    """A node as readable lines: its settings, outputs, form, and where it goes and when."""
    n = mapdb.names(con, sid)

    def show(text: str) -> str:
        return plain(to_designer(text, n)) if text else ""

    row = con.execute(
        "SELECT details FROM node_details WHERE snapshot_id = ? AND pm_uuid = ? AND gui_id = ?",
        (sid, pm, gui),
    ).fetchone()
    d = json.loads(row[0]) if row else {}
    lines = [f"{i['name']}: {show(i['expr']) or i['value']}" for i in d.get("inputs", [])]
    lines += [f"output {o}" for o in d.get("outputs", [])]
    lines += [f"form {show(d['form'])}"] if d.get("form") else []
    for to, kind, label, cond in con.execute(
        "SELECT to_gui, kind, label, condition FROM flows WHERE snapshot_id = ? AND pm_uuid = ? "
        "AND from_gui = ? ORDER BY rowid",
        (sid, pm, gui),
    ):
        lines.append(f"{kind} -> {to} {label or ''} {show(cond or '')}".rstrip())
    return "\n".join(lines)
