"""Permission as configured: which groups hold the role that lets someone use a door.

A visibility rule only shows or hides; the role map on the object behind the door decides who
may actually use it (process models: Initiator; sites, record types, web APIs: Viewer). An
empty answer means the export has no role map for that object, not that everyone may use it.
check() lists the places where what a door shows and what its permission allows disagree.
"""

from __future__ import annotations

import re
from typing import Any

from atg.agent.atlas import Atlas

_ROLE = {
    "processModel": re.compile(r"initiat", re.IGNORECASE),
    "site": re.compile(r"view", re.IGNORECASE),
    "recordType": re.compile(r"view", re.IGNORECASE),
    "webApi": re.compile(r"view|call", re.IGNORECASE),
}


def _group_name(atlas: Atlas, g: str) -> str:
    return atlas.name(g) if atlas.type(g) == "group" else "a group outside this export"


def permission(atlas: Atlas, uuid: str) -> dict[str, Any]:
    kind = atlas.type(uuid)
    pattern = _ROLE.get(kind)
    roles = atlas.det(uuid).get("roles", []) if uuid else []
    if pattern is None or not roles:
        return {"found": False, "says": "no role map for this in the export"}
    held = [r for r in roles if pattern.search(r["role"])]
    groups = sorted({_group_name(atlas, g) for r in held for g in r["groups"]})
    everyone = any(r["everyone"] for r in held)
    says = "everyone" if everyone else ("only " + ", ".join(groups) if groups else "nobody")
    return {
        "found": True,
        "on": atlas.name(uuid),
        "groups": groups,
        "everyone": everyone,
        "says": f"{says} may use it (role map of {atlas.name(uuid)})",
    }


def check(doors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Doors whose visibility and permission disagree, both ways."""
    out = []
    for d in doors:
        perm = d.get("permission", {})
        if not perm.get("found") or perm.get("everyone"):
            continue
        allowed = set(perm["groups"])
        shown = {g for gate in d["gates"] if gate["kind"] == "group" for g in gate["groups"]}
        if not d["gates"]:
            out.append(
                {
                    "door": d["id"],
                    "name": d["name"],
                    "issue": "shown to everyone but only "
                    f"{', '.join(sorted(allowed)) or 'nobody'} may use it: others see it "
                    "and are refused",
                }
            )
        elif shown - allowed:
            out.append(
                {
                    "door": d["id"],
                    "name": d["name"],
                    "issue": f"shown to {', '.join(sorted(shown - allowed))} who may not use it",
                }
            )
    return out
