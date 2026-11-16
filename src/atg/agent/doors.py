"""Every way in, with its trigger, where it opens, its gates and the permission behind it.

  page:<site>:<stub>        a site page          /suite/sites/<site stub>/page/<stub>
  action:<uuid>             a record list or related action (starts a process)
  view:<record type>:<n>    a record view (tab on a record)
  task:<process>:<node>     a user task, reached from the task list
  api:<uuid>                a web API
  start:<process>           a process started by a timer, a message, or nothing found
Gates are visibility (shows or hides); permission is the role map of the object behind.
"""

from __future__ import annotations

import json
import re
from typing import Any

from atg.agent import security, states, triggers
from atg.agent.atlas import Atlas
from atg.agent.effects import TASK, assignee
from atg.agent.gates import gates_in
from atg.read.xmlutil import UUID_RE
from atg.testgen import urls

Door = dict[str, Any]
_TRIGGER = {"web API": "api", "user task": "task"}


def _stub(atlas: Atlas, uuid: str) -> str:
    return next(
        (s["value"] for s in atlas.det(uuid).get("settings", []) if s["label"] == "urlStub"), ""
    )


_LITERAL = re.compile(r'"((?:[^"]|"")+)"')
_CANON = re.compile(r'#"[^"]*"')  # references to objects and functions, not text


def readable(name: str, fallback: str) -> str:
    """A title as a person sees it. Record view and action titles can be SAIL: a quoted text,
    Appian's default summary title, or an expression whose first text is the best guess."""
    text = name.strip().removeprefix("=").strip()
    if "getDefaultSummaryViewName" in text:
        return "Summary"
    if not text:
        return fallback
    if not any(c in text for c in '#"(!'):
        return text  # already plain
    m = _LITERAL.search(_CANON.sub("", text))
    return m.group(1).replace('""', '"') if m else fallback


def doors(atlas: Atlas) -> list[Door]:
    if "doors" not in atlas.memo:
        atlas.memo["doors"] = _doors(atlas)
    out: list[Door] = atlas.memo["doors"]
    return out


def _doors(atlas: Atlas) -> list[Door]:
    out: list[Door] = []
    for uuid, (kind, name) in atlas.objects.items():
        d = atlas.det(uuid)
        if kind == "site":
            base = f"/suite/sites/{_stub(atlas, uuid)}/page/"
            for p in d.get("pages", []):
                key = f"page:{uuid}:{p['stub'] or p['name']}"
                out.append(
                    _door(
                        atlas,
                        key,
                        "site page",
                        p["name"],
                        p["target"],
                        p["visibility"],
                        base + p["stub"],
                        uuid,
                        uuid,
                    )
                )
        elif kind == "recordType":
            stub = _stub(atlas, uuid)
            where = f"/suite/tempo/records/type/{stub}/view/all" if stub else ""
            for a in d.get("actions", []):
                out.append(
                    _door(
                        atlas,
                        f"action:{a['uuid']}",
                        a["kind"],
                        readable(a["name"], "action"),
                        a["target"],
                        a.get("visibility", ""),
                        where,
                        uuid,
                        a["target"],
                    )
                )
            for i, v in enumerate(d.get("views", [])):
                ui = next((u for u in UUID_RE.findall(v["expression"]) if u in atlas.objects), "")
                tab = f"{where} (open a record, tab {v.get('stub', '')})"
                out.append(
                    _door(
                        atlas,
                        f"view:{uuid}:{i}",
                        "record view",
                        readable(v["name"], f"view {i + 1}"),
                        ui,
                        v.get("visibility", ""),
                        tab,
                        uuid,
                        uuid,
                    )
                )
        elif kind == "webApi":
            out.append(_door(atlas, f"api:{uuid}", "web API", name, uuid, "", "", "", uuid))
    out += _tasks(atlas)
    for s in triggers.start_doors(atlas):
        pm = s["pm"]
        door = _door(
            atlas, f"start:{pm}", f"{s['trigger']} start", atlas.name(pm), pm, "", "", "", pm
        )
        door["trigger"] = s["trigger"]
        out.append(door)
    return out


def _tasks(atlas: Atlas) -> list[Door]:
    out = []
    for pm, gui, label, asg, det in atlas.con.execute(
        "SELECT n.pm_uuid, n.gui_id, n.label, n.assignees, d.details FROM nodes n "
        "LEFT JOIN node_details d ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid "
        "AND d.gui_id = n.gui_id WHERE n.snapshot_id = ? AND n.type_id = ?",
        (atlas.sid, TASK),
    ):
        who = [assignee(a, atlas) for a in json.loads(asg or "[]")]
        form = json.loads(det or "{}").get("form", "")
        opens = next((u for u in UUID_RE.findall(form) if atlas.type(u) == "interface"), pm)
        door = _door(atlas, f"task:{pm}:{gui}", "user task", label, opens, "", urls.TASKS, pm, "")
        door["gates"] = [
            {
                "kind": "assigned",
                "groups": who,
                "confidence": "read",
                "says": "assigned to " + (", ".join(who) or "nobody set"),
                "where": "whole",
                "guard": "assignment",
            }
        ]
        out.append(door)
    return out


def _door(
    atlas: Atlas,
    key: str,
    kind: str,
    name: str,
    target: str,
    gate: str,
    url: str,
    owner: str,
    secured_by: str,
) -> Door:
    return {
        "id": key,
        "kind": kind,
        "trigger": _TRIGGER.get(kind, "user"),
        "name": name,
        "in": atlas.name(owner) if owner else "",
        "in_id": owner,
        "url": url,
        "opens": atlas.ref(target) if target else None,
        "gates": gates_in(atlas, gate) if gate else [],
        "permission": security.permission(atlas, secured_by),
        "needs_state": states.predicates(atlas, gate),
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
