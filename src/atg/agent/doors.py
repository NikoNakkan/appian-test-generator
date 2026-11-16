"""The ways a user gets in, each with where it opens and its gate as written in the export.

page:<site>:<stub>        a site page          /suite/sites/<site stub>/page/<stub>
action:<uuid>             a record list or related action (starts a process)
view:<record type>:<n>    a record view (tab on a record)
task:<process>:<node>     a user task, reached from the task list
api:<uuid>                a web API
"""

from __future__ import annotations

import json
from typing import Any

from atg.agent.atlas import Atlas
from atg.agent.effects import TASK, assignee
from atg.agent.gates import gates_in
from atg.read.xmlutil import UUID_RE
from atg.testgen import urls

Door = dict[str, Any]


def _stub(atlas: Atlas, uuid: str) -> str:
    return next(
        (s["value"] for s in atlas.det(uuid).get("settings", []) if s["label"] == "urlStub"), ""
    )


def doors(atlas: Atlas) -> list[Door]:
    if "doors" not in atlas.memo:
        atlas.memo["doors"] = _doors(atlas)
    out: list[Door] = atlas.memo["doors"]
    return out


def _doors(atlas: Atlas) -> list[Door]:
    out: list[Door] = []
    for uuid, (kind, name) in atlas.objects.items():
        if kind == "site":
            site = _stub(atlas, uuid)
            for p in atlas.det(uuid).get("pages", []):
                out.append(
                    _door(
                        atlas,
                        f"page:{uuid}:{p['stub'] or p['name']}",
                        "site page",
                        p["name"],
                        p["target"],
                        p["visibility"],
                        f"/suite/sites/{site}/page/{p['stub']}",
                        name,
                    )
                )
        elif kind == "recordType":
            d = atlas.det(uuid)
            stub = _stub(atlas, uuid)
            where = f"/suite/tempo/records/type/{stub}/view/all" if stub else ""
            for a in d.get("actions", []):
                out.append(
                    _door(
                        atlas,
                        f"action:{a['uuid']}",
                        a["kind"],
                        a["name"],
                        a["target"],
                        a.get("visibility", ""),
                        where,
                        name,
                    )
                )
            for i, v in enumerate(d.get("views", [])):
                target = next(
                    (u for u in UUID_RE.findall(v["expression"]) if u in atlas.objects), ""
                )
                out.append(
                    _door(
                        atlas,
                        f"view:{uuid}:{i}",
                        "record view",
                        v["name"].strip('"') or "view",
                        target,
                        v.get("visibility", ""),
                        where + f" (open a record, tab {v.get('stub', '')})",
                        name,
                    )
                )
        elif kind == "webApi":
            out.append(_door(atlas, f"api:{uuid}", "web API", name, uuid, "", "", ""))
    for pm, gui, label, asg, det in atlas.con.execute(
        "SELECT n.pm_uuid, n.gui_id, n.label, n.assignees, d.details FROM nodes n "
        "LEFT JOIN node_details d ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid "
        "AND d.gui_id = n.gui_id WHERE n.snapshot_id = ? AND n.type_id = ?",
        (atlas.sid, TASK),
    ):
        who = [assignee(a, atlas) for a in json.loads(asg or "[]")]
        form = json.loads(det or "{}").get("form", "")
        opens = next((u for u in UUID_RE.findall(form) if atlas.type(u) == "interface"), pm)
        door = _door(
            atlas, f"task:{pm}:{gui}", "user task", label, opens, "", urls.TASKS, atlas.name(pm)
        )
        door["gates"] = [
            {
                "kind": "assigned",
                "groups": who,
                "says": "assigned to " + (", ".join(who) or "nobody set"),
                "confidence": "read",
                "where": "whole",
            }
        ]
        out.append(door)
    return out


def _door(
    atlas: Atlas, key: str, kind: str, name: str, target: str, gate: str, url: str, owner: str
) -> Door:
    return {
        "id": key,
        "kind": kind,
        "name": name,
        "in": owner,
        "url": url,
        "opens": atlas.ref(target) if target else None,
        "gates": gates_in(atlas, gate) if gate else [],
        "gate_as_written": gate[:300],
    }


def by_id(atlas: Atlas, key: str) -> Door | None:
    return next((d for d in doors(atlas) if d["id"] == key), None)


def leading_to(atlas: Atlas, uuid: str, depth: int = 100) -> list[Door]:
    """Doors whose target reaches this object (it is the target, or used under it)."""
    above, frontier = {uuid}, {uuid}
    for _ in range(depth):
        frontier = {
            u for f in frontier for u in atlas.used_by.get(f, []) if atlas.type(u) not in _STOP
        } - above
        if not frontier:
            break
        above |= frontier
    return [d for d in doors(atlas) if d["opens"] and d["opens"]["id"] in above]


_STOP = frozenset({"site", "recordType", "application", "folder", "rulesFolder", "group"})
