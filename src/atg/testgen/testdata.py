"""The data a test needs before it can run: a schema per test path and per rule.

Path: process inputs to start with (and their fields), what each gateway needs the data to be,
what people fill in at user tasks, what the run computes itself, database records it reads and
writes, sub-processes it starts and outside systems it calls.
Rule: its inputs (and their fields), the values worth trying (from its comparisons, empty
checks and loops), and the records and outside systems it reaches.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from atg import mapdb
from atg.layers import feature_engine
from atg.read.xmlutil import UUID_RE
from atg.sail.display import Names
from atg.sail.explain import phrase, split_output, target_name
from atg.testgen import forms

_PRIMITIVE = {
    "Text",
    "Integer",
    "Boolean",
    "Decimal",
    "Date",
    "Date and time",
    "Time",
    "Variant",
    "Map",
    "Dictionary",
    "User",
    "Group",
    "Document",
    "Folder",
}
_EMPTY = {"null", '""', "{}"}
_AC = re.compile(r"\bac!(\w+)")
_PV = re.compile(r"\bpv!(\w+)")
_RI = re.compile(r"\bri!(\w+)")
_WRITES = ("internal3.write_records", "appian.system.smart-services.write-to-data-store")
_DELETES = ("internal3.delete_records", "appian.system.smart-services.delete-from-data-store")


def schema(con: sqlite3.Connection, sid: int, type_name: str, n: Names) -> dict[str, Any]:
    """Fields of a type: a record type (stored by UUID), one of the app's data types, or unknown."""
    base = type_name.removesuffix(" (list)")
    many = type_name.endswith(" (list)")
    if base in _PRIMITIVE or not base:
        return {"type": type_name, "kind": "value", "list": many}
    if base in n.objects and n.objects[base][0] == "recordType":
        fields = mapdb.details(con, sid, base).get("fields", [])
        return {
            "type": n.objects[base][1] + (" (list)" if many else ""),
            "kind": "record",
            "list": many,
            "fields": [{"name": f["name"], "type": f["type"]} for f in fields],
        }
    for u, (kind, name) in n.objects.items():
        if kind == "datatype" and name == base:
            return {
                "type": type_name,
                "kind": "data type",
                "list": many,
                "fields": mapdb.details(con, sid, u).get("fields", []),
            }
    return {"type": type_name, "kind": "outside this export", "list": many}


def _reach(con: sqlite3.Connection, sid: int, starts: set[str]) -> dict[str, set[str]]:
    """Record types, integrations and connected systems reachable from these objects."""
    types, succ = feature_engine.graph(con, sid)
    found: dict[str, set[str]] = {
        "recordType": set(),
        "integration": set(),
        "connectedSystem": set(),
    }
    for s in starts:
        if types.get(s) == "processModel":
            continue  # started processes are tested on their own
        for m in feature_engine.reach(s, types, succ):
            if types.get(m) in found:
                found[types[m]].add(m)
    return found


def path_data(con: sqlite3.Connection, sid: int, pm: str, path_no: int) -> dict[str, Any]:
    n = mapdb.names(con, sid)
    row = con.execute(
        "SELECT steps, decisions, calls FROM paths WHERE snapshot_id = ? "
        "AND pm_uuid = ? AND path_no = ?",
        (sid, pm, path_no),
    ).fetchone()
    if row is None:
        return {"error": "No such test path."}
    steps, decisions, calls = json.loads(row[0]), json.loads(row[1]), json.loads(row[2])
    variables = {v["name"]: v for v in mapdb.details(con, sid, pm).get("variables", [])}
    nodes = {
        g: (t, lab or tn, json.loads(d or "{}"), json.loads(a or "[]"))
        for g, t, lab, tn, d, a in con.execute(
            "SELECT n.gui_id, n.type_id, n.label, n.type_name, d.details, n.assignees FROM nodes n "
            "LEFT JOIN node_details d ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid "
            "AND d.gui_id = n.gui_id WHERE n.snapshot_id = ? AND n.pm_uuid = ?",
            (sid, pm),
        )
    }
    on_path = [g for g in dict.fromkeys(steps) if g in nodes]

    def var(name: str) -> dict[str, Any]:
        v = variables.get(name, {"name": name, "type": ""})
        return {"name": name, **schema(con, sid, v["type"], n)}

    conditions = [
        {
            "gateway": nodes.get(d["gateway"], ("", "", {}, []))[1],
            "choice": d["rule"],
            "needs": [p for p in [phrase(d["must_be_true"], n)] if p]
            + [phrase(c, n, negate=True) for c in d["must_be_false"]],
            "variables": sorted(set(_PV.findall(d["must_be_true"] + " ".join(d["must_be_false"])))),
        }
        for d in decisions
    ]
    tasks, computed, written, deleted, refs = [], [], set(), set(), set()
    for g in on_path:
        type_id, label, det, assignees = nodes[g]
        outputs = [split_output(o) for o in det.get("outputs", [])]
        node_refs = set(UUID_RE.findall(json.dumps(det)))
        refs |= node_refs
        if type_id == "internal.17":
            places = forms.task_fills(con, sid, det.get("form", ""))
            fills = [
                {
                    "variable": target_name(t, n),
                    "from_form": ", ".join(_AC.findall(e)) or e[:60],
                    "where": [p for ac in _AC.findall(e) for p in places.get(ac, [])],
                }
                for t, e in outputs
            ]
            tasks.append(
                {
                    "task": label,
                    "groups": [n.objects.get(a, ("", a))[1] for a in assignees],
                    "fills": fills,
                }
            )
        else:
            computed += [{"variable": target_name(t, n), "by": label} for t, _ in outputs]
        touched = {r for r in node_refs if n.objects.get(r, ("",))[0] == "recordType"}
        if type_id.startswith(_WRITES):
            written |= touched
        if type_id.startswith(_DELETES):
            deleted |= touched
    reached = _reach(con, sid, refs)
    used_vars = {v for c in conditions for v in c["variables"]}
    return {
        "start_inputs": [var(k) for k, v in variables.items() if v.get("parameter")],
        "conditions": conditions,
        "condition_variables": [var(v) for v in sorted(used_vars)],
        "user_tasks": tasks,
        "computed": computed,
        "records_read": records(con, sid, reached["recordType"] - written - deleted, n),
        "records_written": records(con, sid, written, n),
        "records_deleted": records(con, sid, deleted, n),
        "outside_systems": named(reached["integration"] | reached["connectedSystem"], n),
        "subprocesses": [{"name": n.objects.get(c, ("", "outside this export"))[1]} for c in calls],
    }


def rule_data(con: sqlite3.Connection, sid: int, uuid: str) -> dict[str, Any]:
    n = mapdb.names(con, sid)
    d = mapdb.details(con, sid, uuid)
    tries: dict[str, list[str]] = {}
    for kind, cond, lits in con.execute(
        "SELECT kind, condition, literals FROM branches WHERE snapshot_id = ? AND owner_uuid = ?",
        (sid, uuid),
    ):
        for name in _RI.findall(cond):
            hints = tries.setdefault(name, [])
            if kind == "null_check":
                hints.append("empty and filled in")
            elif kind == "loop":
                hints.append("0, 1 and several items")
            elif kind == "compare":
                hints += [f"just below, at and above {v}" for v in json.loads(lits)]
    saved = d.get("saved_tests", [])
    inputs = [
        {
            "name": i["name"],
            "description": i.get("description", ""),
            **schema(con, sid, i["type"], n),
            "try": sorted(set(tries.get(i["name"], []))),
            "saved": sorted(
                {
                    target_name(v, n)
                    for t in saved
                    if (v := t["inputs"].get(i["name"], "null")) not in _EMPTY
                }
            )[:5],
        }
        for i in d.get("inputs", [])
    ]
    reached = _reach(con, sid, {uuid})
    return {
        "inputs": inputs,
        "saved_tests": [t["name"] or "(no name)" for t in saved],
        "records_read": records(con, sid, reached["recordType"], n),
        "outside_systems": named(reached["integration"] | reached["connectedSystem"], n),
    }


def records(con: sqlite3.Connection, sid: int, uuids: set[str], n: Names) -> list[dict[str, Any]]:
    """Record types with what setting up their rows takes: table, sync, related records,
    and fields Appian computes itself."""
    out = []
    for r in named(uuids, n):
        d = mapdb.details(con, sid, r["uuid"])
        src = d.get("source", {})
        out.append(
            {
                **r,
                "source": src.get("kind", ""),
                "table": src.get("table", ""),
                "sync": src.get("sync", {}),
                "related": [
                    {"name": n.objects.get(x["target"], ("", x["name"]))[1], "kind": x["kind"]}
                    for x in d.get("relationships", [])
                ],
                "computed": [f["name"] for f in d.get("fields", []) if f.get("computed")],
            }
        )
    return out


def named(uuids: set[str], n: Names) -> list[dict[str, str]]:
    return sorted(
        ({"uuid": u, "name": n.objects[u][1]} for u in uuids if u in n.objects),
        key=lambda x: x["name"],
    )
