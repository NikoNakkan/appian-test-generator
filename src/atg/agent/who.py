"""Who can reach what: the gates on the way to an object, and everything one group can reach.

A door with no gate is open to anyone who can open the app (Appian's own object security is
not in the export). "Own data" and "profile" gates mean two users of the same group may see
different things: the agent should try both.
"""

from __future__ import annotations

from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas
from atg.agent.cards import cut
from atg.agent.gates import gates_in, group_ids


def who(atlas: Atlas, key: str) -> dict[str, Any]:
    door = doors.by_id(atlas, key)
    if door is not None:
        return {"id": key, "name": door["name"], "gates": door["gates"] or [_OPEN]}
    leading = doors.leading_to(atlas, key)
    return {
        "id": key,
        "name": atlas.name(key),
        "inside": gates_in(atlas, atlas.text(key), "part"),
        "through": [
            {"door": d["id"], "kind": d["kind"], "name": d["name"], "gates": d["gates"] or [_OPEN]}
            for d in leading[:20]
        ],
    }


_OPEN = {"kind": "none", "groups": [], "says": "no gate in the export", "confidence": "read"}


def _group(atlas: Atlas, group: str) -> str:
    if atlas.type(group) == "group":
        return group
    low = group.lower()
    return next((u for u, (t, n) in atlas.objects.items() if t == "group" and n.lower() == low), "")


def visible_to(atlas: Atlas, group: str) -> dict[str, Any]:
    gid = _group(atlas, group)
    if not gid:
        return {"error": f"no group {group!r} in this export"}
    name = atlas.name(gid)
    all_doors = doors.doors(atlas)
    gated = [d for d in all_doors if any(name in g["groups"] for g in d["gates"])]
    open_ = [d for d in all_doors if not d["gates"]]
    own = [d for d in all_doors if any(g["kind"] in {"own data", "profile"} for g in d["gates"])]
    parts = [
        atlas.ref(u)
        for u, (t, _) in atlas.objects.items()
        if t == "interface" and gid in group_ids(atlas, atlas.text(u))
    ]
    return {
        "group": name,
        "doors_for_this_group": cut([_brief(d) for d in gated]),
        "screens_with_parts_only_for_it": cut(parts),
        "doors_with_no_gate": cut([_brief(d) for d in open_], 15),
        "doors_that_depend_on_the_user": cut([_brief(d) for d in own], 15),
        "note": "doors gated to other groups should be hidden or refused for this group",
    }


def _brief(d: dict[str, Any]) -> dict[str, Any]:
    return {"id": d["id"], "kind": d["kind"], "name": d["name"], "url": d["url"]}
