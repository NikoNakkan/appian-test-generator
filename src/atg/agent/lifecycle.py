"""Each record type against create, read, update, delete and the statuses set, as an
independent check on the door view: a record type nothing creates or deletes may mean a
missing feature, another app, or data loaded outside Appian. Gaps are questions, not defects.

Writes come from process nodes (write records, a!update / a record built by its type) and from
screen buttons; reads from screens, rules and web APIs that use the record type; statuses from
values written into status-like fields.
"""

from __future__ import annotations

import json
import re
from typing import Any

from atg.agent.atlas import Atlas
from atg.agent.effects import SET_FIELD
from atg.agent.states import statusish
from atg.sail import actions

_READERS = frozenset({"interface", "rule", "decision", "webApi"})


def _record_type_of(atlas: Atlas) -> dict[str, str]:
    """Field uuid -> record type uuid."""
    out = {}
    for u, (t, _) in atlas.objects.items():
        if t == "recordType":
            out.update({f["uuid"]: u for f in atlas.det(u).get("fields", [])})
    return out


def lifecycle(atlas: Atlas) -> list[dict[str, Any]]:
    owner = _record_type_of(atlas)
    rows: dict[str, dict[str, Any]] = {
        u: {
            "record_type": n,
            "id": u,
            "create": [],
            "read": [],
            "update": [],
            "delete": [],
            "statuses_set": {},
        }
        for u, (t, n) in atlas.objects.items()
        if t == "recordType"
    }
    for pm, gui, type_name, det in atlas.con.execute(
        "SELECT n.pm_uuid, n.gui_id, n.type_name, d.details FROM nodes n JOIN node_details d "
        "ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid AND d.gui_id = n.gui_id "
        "WHERE n.snapshot_id = ?",
        (atlas.sid,),
    ):
        code = json.dumps(json.loads(det or "{}").get("inputs", []))
        where = f"{atlas.name(pm)}: node {gui}"
        kind = type_name.lower()
        for rt, row in rows.items():
            if rt not in code:
                continue
            if "delete" in kind:
                row["delete"].append(where)
            elif "write" in kind or "update" in code:
                built = re.search(rf'record-type:v\d+:{rt}\\?"\(', code)
                row["create" if built else "update"].append(where)
        for field, value in SET_FIELD.findall(code.replace('\\"', '"')):
            rt = owner.get(field, "")
            name = atlas.names.fields.get(field, "")
            if rt in rows and statusish(name):
                rows[rt]["statuses_set"].setdefault(name, [])
                if value not in rows[rt]["statuses_set"][name]:
                    rows[rt]["statuses_set"][name].append(value)
    for ui, (t, _) in atlas.objects.items():
        if t == "interface":
            for a in actions.find(atlas.text(ui)):
                for rt in a.writes:
                    if rt in rows:
                        rows[rt]["update"].append(f'{atlas.name(ui)}: button "{a.label}"')
                for rt in a.deletes:
                    if rt in rows:
                        rows[rt]["delete"].append(f'{atlas.name(ui)}: button "{a.label}"')
    for rt, row in rows.items():
        row["read"] = [
            atlas.name(u) for u in atlas.used_by.get(rt, []) if atlas.type(u) in _READERS
        ]
        row["gaps"] = _gaps(atlas, rt, row)
    return list(rows.values())


def _gaps(atlas: Atlas, rt: str, row: dict[str, Any]) -> list[str]:
    out = []
    if not row["create"] and not row["update"]:
        out.append("nothing in this export writes it (another app, or loaded outside Appian?)")
    if not row["delete"]:
        out.append("nothing deletes it (kept forever, or deleted elsewhere?)")
    if not row["read"]:
        out.append("no screen or rule reads it")
    has_status = any(statusish(f["name"]) for f in atlas.det(rt).get("fields", []))
    if has_status and not row["statuses_set"]:
        out.append("it has a status field but no status value is written here")
    return out
