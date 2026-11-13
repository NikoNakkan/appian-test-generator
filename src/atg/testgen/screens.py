"""Screens: the interfaces a person actually opens, and how they get there.

Not every screen lives in a process. A screen is an interface that something outside the
interface layer shows: a site page, a record view, a process start form (often behind a record
action), or a user task form. Interfaces only used inside other interfaces are parts of a
screen, not screens of their own. A screen's buttons may save, write records or start a
process directly, with no process model in between.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from typing import Any

from atg import mapdb
from atg.layers import feature_engine
from atg.read.xmlutil import UUID_RE
from atg.sail import actions
from atg.sail.display import Names
from atg.testgen import forms, testdata, urls

_PARTS = frozenset({"interface", "rule", "decision", "constant"})
_UPLOAD = re.compile(r"fileUploadField", re.IGNORECASE)


def routes(con: sqlite3.Connection, sid: int) -> dict[str, list[dict[str, str]]]:
    """For each screen: every way a person reaches it."""
    types = dict(con.execute("SELECT uuid, type FROM objects WHERE snapshot_id = ?", (sid,)))
    names = dict(con.execute("SELECT uuid, name FROM objects WHERE snapshot_id = ?", (sid,)))
    found: dict[str, list[dict[str, str]]] = {}
    pages, lists = urls.site_pages(con, sid), urls.record_lists(con, sid)

    def add(ui: str, how: str, where: str, owner: str = "", url: str = "") -> None:
        if types.get(ui) == "interface":
            route = {"how": how, "where": where, "owner": owner, "url": url}
            found.setdefault(ui, []).append(route)

    entries = list(
        con.execute(
            "SELECT kind, name, target, owner_uuid FROM entry_points WHERE snapshot_id = ?",
            (sid,),
        )
    )
    for kind, name, target, _ in entries:
        if kind == "site page":
            add(target, "site page", name, url=pages.get(target, ""))
    task_forms: set[tuple[str, str]] = set()
    for pm, label, det in con.execute(
        "SELECT n.pm_uuid, n.label, d.details FROM nodes n JOIN node_details d "
        "ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid AND d.gui_id = n.gui_id "
        "WHERE n.snapshot_id = ? AND n.type_id = 'internal.17'",
        (sid,),
    ):
        for ui in set(UUID_RE.findall(json.loads(det or "{}").get("form", ""))):
            task_forms.add((pm, ui))
            add(ui, "user task", f"{label} in {names.get(pm, pm)}", pm, urls.TASKS)
    started_by: dict[str, list[str]] = {}
    list_of: dict[str, str] = {}
    for kind, name, target, owner in entries:
        if kind != "site page":
            started_by.setdefault(target, []).append(f"{kind} “{name}”")
            list_of.setdefault(target, lists.get(owner, ""))
    for src, target, kind in con.execute(
        "SELECT DISTINCT source_uuid, target, kind FROM refs WHERE snapshot_id = ?", (sid,)
    ):
        if types.get(src) == "recordType" and kind == "sail":
            add(target, "record view", names.get(src, src), src, lists.get(src, ""))
        elif types.get(src) == "processModel" and kind == "xml" and (src, target) not in task_forms:
            via = ", ".join(started_by.get(src, [])) or "started by another process or outside"
            add(target, "start form", f"{names.get(src, src)} ({via})", src, list_of.get(src, ""))
    used = {
        t
        for s, t in con.execute(
            "SELECT DISTINCT source_uuid, target FROM refs WHERE snapshot_id = ?", (sid,)
        )
        if s != t and types.get(s) not in feature_engine.CONTAINERS
    }
    for ui, kind in types.items():
        if kind == "interface" and ui not in found and ui not in used:
            add(ui, "not shown anywhere", "nothing in this export opens it; maybe another app does")
    return found


def _parts(start: str, types: dict[str, str], succ: dict[str, set[str]]) -> set[str]:
    """Everything the screen itself reaches, stopping at processes it starts."""
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in succ.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                if types.get(nxt) in _PARTS:
                    queue.append(nxt)
    return seen


def screen_data(con: sqlite3.Connection, sid: int, uuid: str) -> dict[str, Any]:
    n = mapdb.names(con, sid)
    types, succ = feature_engine.graph(con, sid)
    reached = _parts(uuid, types, succ)
    texts = [
        t
        for o, t in con.execute(
            "SELECT owner_uuid, text FROM expressions WHERE snapshot_id = ? "
            "AND location = 'definition'",
            (sid,),
        )
        if types.get(o) == "interface" and o in reached
    ]
    found = [a for t in texts for a in actions.find(t)]
    written = {u for a in found for u in a.writes}
    deleted = {u for a in found for u in a.deletes}

    def of(kind: str) -> set[str]:
        return {u for u in reached if types.get(u) == kind}

    started = {u for a in found for u in a.starts}
    base = testdata.rule_data(con, sid, uuid)
    return {
        "inputs": base["inputs"],
        "saved_tests": base["saved_tests"],
        "routes": routes(con, sid).get(uuid, []),
        "parts": len(of("interface")) - 1,
        "fields": forms.form_fields(con, sid, uuid),
        "actions": [_describe(con, sid, a, n) for a in found],
        "file_uploads": sum(len(_UPLOAD.findall(t)) for t in texts),
        "records_read": testdata.records(con, sid, of("recordType") - written - deleted, n),
        "records_written": testdata.records(con, sid, written, n),
        "records_deleted": testdata.records(con, sid, deleted, n),
        "processes_started": testdata.named(started | (of("processModel") - started), n),
        "outside_systems": testdata.named(of("integration") | of("connectedSystem"), n),
    }


def upload_fields(con: sqlite3.Connection, sid: int, uuid: str) -> int:
    """File upload fields on a screen and the interfaces it is built from."""
    types, succ = feature_engine.graph(con, sid)
    reached = _parts(uuid, types, succ)
    return sum(
        len(_UPLOAD.findall(t))
        for o, t in con.execute(
            "SELECT owner_uuid, text FROM expressions WHERE snapshot_id = ? "
            "AND location = 'definition'",
            (sid,),
        )
        if o in reached
    )


def _describe(con: sqlite3.Connection, sid: int, a: actions.Action, n: Names) -> dict[str, Any]:
    """An action in words: its label and what it does, with names instead of UUIDs."""
    does = []
    if a.submits:
        does.append("submits the form")
    for ref in a.record_actions:
        rt, action = ref.split("/")
        found = next((x for x in mapdb.details(con, sid, rt).get("actions", [])
                      if x["uuid"] == action), None)  # fmt: skip
        if found:
            target = n.objects.get(found["target"], ("", "a process outside this export"))[1]
            does.append(f"opens the {found['kind']} “{found['name']}” (starts {target})")
        else:
            does.append("opens a record action from another app")
    for u in a.starts:
        kind, name = n.objects.get(u, ("", "a process from another app"))
        does.append(
            f"starts the process in constant {name}" if kind == "constant" else f"starts {name}"
        )
    does += [f"writes {n.objects.get(u, ('', u))[1]}" for u in a.writes]
    does += [f"deletes {n.objects.get(u, ('', u))[1]}" for u in a.deletes]
    if a.saves and not does:
        does.append("updates values on the screen")
    label = a.label or next((d.split("“")[1].split("”")[0] for d in does if "“" in d), "(no label)")
    return {"kind": a.kind, "label": label, "does": does or ["nothing the export shows"]}
