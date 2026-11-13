"""Read-only Designer views: one object's page and one process node's properties.

Code is shown in Designer form (sail/display.py) as segments [text, uuid|"outside"|null], so
the browser can highlight it and link each reference. Code itself is never translated.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from atg import mapdb
from atg.sail.display import Names, Segment, plain, to_designer
from atg.sail.explain import phrase, split_output, target_name

_TASKS = {"internal.17"}
# Engine settings Designer doesn't show as inputs (the called process is shown on its own).
_HIDDEN_INPUTS = frozenset(
    {
        "pmID",
        "pmUUID",
        "subProcessID",
        "procInheritsPriority",
        "isTransparent",
        "inheritSecurity",
        "chainsInto",
    }
)
# Sub-process parameter maps: oneInputMap {sppn: name, sppv: value} -> "name <- value".
_MAPS = {"inMap": "Input variables", "outMap": "Output variables"}
_GATEWAYS = {"core.3", "core.4", "core.5"}


def _code(text: str, n: Names) -> list[Segment]:
    return to_designer(text, n) if text else []


def object_page(con: sqlite3.Connection, sid: int, uuid: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT type, name FROM objects WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
    ).fetchone()
    if row is None:
        return {"error": "No such object in this snapshot."}
    kind, name = row
    n = mapdb.names(con, sid)
    raw = con.execute(
        "SELECT details FROM object_details WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
    ).fetchone()
    d: dict[str, Any] = json.loads(raw[0]) if raw else {}
    definition = con.execute(
        "SELECT text FROM expressions WHERE snapshot_id = ? AND owner_uuid = ? "
        "AND location = 'definition'",
        (sid, uuid),
    ).fetchone()
    for s in d.get("settings", []):
        s["segments"] = _code(s["value"], n) if s.get("code") else None
    for v in d.get("views", []):
        v["segments"] = _code(v.get("expression", ""), n)
        v["name"] = plain(_code(v.get("name", ""), n)).strip('"')
    for f in d.get("fields", []):
        f["segments"] = _code(f.get("expression", ""), n)
    return {
        "uuid": uuid,
        "type": kind,
        "name": name,
        "description": d.get("description", "") if d.get("description") else "",
        "details": d,
        "code": _code(definition[0], n) if definition else [],
        "entry_points": [
            {
                "kind": k,
                "name": nm,
                "target": t,
                "target_name": n.objects.get(t, ("", "outside this export"))[1],
            }
            for k, nm, t in con.execute(
                "SELECT kind, name, target FROM entry_points WHERE snapshot_id = ? "
                "AND owner_uuid = ?",
                (sid, uuid),
            )
        ],
    }


def node_page(con: sqlite3.Connection, sid: int, pm: str, gui: int) -> dict[str, Any]:
    row = con.execute(
        "SELECT type_id, type_name, label, assignees, calls FROM nodes "
        "WHERE snapshot_id = ? AND pm_uuid = ? AND gui_id = ?",
        (sid, pm, gui),
    ).fetchone()
    if row is None:
        return {"error": "No such node."}
    type_id, type_name, label, assignees, calls = row
    n = mapdb.names(con, sid)
    raw = con.execute(
        "SELECT details FROM node_details WHERE snapshot_id = ? AND pm_uuid = ? AND gui_id = ?",
        (sid, pm, gui),
    ).fetchone()
    d: dict[str, Any] = json.loads(raw[0]) if raw else {"inputs": [], "outputs": [], "form": ""}
    labels = dict(
        con.execute(
            "SELECT gui_id, COALESCE(NULLIF(label, ''), type_name) FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    )
    rules = [
        {
            "label": "default" if kind == "gateway_default" else lab or "rule",
            "to": labels.get(to, str(to)),
            "kind": kind,
            "segments": _code(cond or "", n),
            "phrase": phrase(cond or "", n),
        }
        for to, kind, lab, cond in con.execute(
            "SELECT to_gui, kind, label, condition FROM flows WHERE snapshot_id = ? "
            "AND pm_uuid = ? AND from_gui = ? AND kind != 'connection' ORDER BY rowid",
            (sid, pm, gui),
        )
    ]
    objects = {u: (t, nm) for u, (t, nm) in n.objects.items()}
    return {
        "gui": gui,
        "type_id": type_id,
        "type_name": type_name,
        "label": label or type_name,
        "inputs": [_input(i, n) for i in d.get("inputs", []) if i["name"] not in _HIDDEN_INPUTS],
        "outputs": [_output(o, n) for o in d.get("outputs", [])],
        "form": _code(d.get("form", ""), n),
        "assignees": [mapdb.assignee_name(a, objects) for a in json.loads(assignees or "[]")],
        "calls": {"uuid": calls, "name": n.objects.get(calls, ("", "outside this export"))[1]}
        if calls
        else None,
        "is_task": type_id in _TASKS,
        "is_gateway": type_id in _GATEWAYS,
        "rules": rules,
    }


def _input(i: dict[str, Any], n: Names) -> dict[str, Any]:
    kids = {c["name"]: c for c in i["children"]}
    if "sppn" in kids:  # one sub-process parameter: show it as "name <- value"
        value = kids.get("sppv", {"expr": "", "type": "", "value": ""})
        return {
            "name": kids["sppn"]["value"],
            "value": value["value"],
            "type": value["type"],
            "saves_into": "",
            "segments": _code(value["expr"], n),
            "children": [],
        }
    return {
        "name": _MAPS.get(i["name"], i["name"]),
        "value": i["value"],
        "type": i["type"],
        "saves_into": i["saves_into"],
        "segments": _code(i["expr"], n),
        "children": [_input(c, n) for c in i["children"]],
    }


def _output(text: str, n: Names) -> dict[str, Any]:
    """`target:expression` -> the variable it sets and the expression, Designer style."""
    target, expr = split_output(text)
    return {"target": target_name(target, n), "segments": _code(expr, n)}
