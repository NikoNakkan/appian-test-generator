"""The kinds of actor the export shows, each with the doors it is linked to and how.

An export has no users and no group members, so these are actor classes: groups named in
gates, role maps and task assignments; relationships (the person who started a process, the
owner of a record); profile-based conditions; and non-human starters (API callers, timers,
messages). "Anyone who can open the app" collects doors with no gate and no role map found.
"""

from __future__ import annotations

from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas
from atg.agent.gates import gates_in

_SYSTEM = {
    "api": "an API caller",
    "timer": "the system, on a timer (runs as the process designer)",
    "message": "the system, when a message arrives",
    "none found": "an unknown starter (another app, or nothing)",
}
_INITIATOR = "the person who started it"


def actors(atlas: Atlas) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def add(actor: str, kind: str, door: dict[str, Any], how: str) -> None:
        a = found.setdefault(actor, {"actor": actor, "kind": kind, "links": {}})
        a["links"].setdefault(door["id"], {"door": door["id"], "name": door["name"], "how": []})
        if how not in a["links"][door["id"]]["how"]:
            a["links"][door["id"]]["how"].append(how)

    for d in doors.doors(atlas):
        if d["trigger"] in _SYSTEM:
            add(_SYSTEM[d["trigger"]], "system", d, "starts it")
        screen = (d["opens"] or {}).get("id", "")
        parts = (
            gates_in(atlas, atlas.text(screen), "part") if atlas.type(screen) == "interface" else []
        )
        for g in [*d["gates"], *parts]:
            if g["kind"] in {"group", "assigned"}:
                for name in g["groups"]:
                    is_rel = name == _INITIATOR
                    how = "gets the task" if g["kind"] == "assigned" else "is shown it"
                    add(name, "relationship" if is_rel else "group", d, how)
            elif g["kind"] == "own data":
                add("the record's own user (owner or creator)", "relationship", d, "own data")
            elif g["kind"] == "profile":
                add("users with particular profile values", "attribute", d, "profile check")
        perm = d.get("permission", {})
        for name in perm.get("groups", []):
            add(name, "group", d, "may use it (role map)")
        if not d["gates"] and not perm.get("groups") and d["trigger"] == "user":
            add("anyone who can open the app", "everyone", d, "no gate or role map found")
    out = []
    for a in found.values():
        links = list(a.pop("links").values())
        out.append({**a, "doors": len(links), "links": links[:25]})
    return sorted(out, key=lambda a: (a["kind"], a["actor"].lower()))
