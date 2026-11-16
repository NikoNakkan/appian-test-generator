"""How to get to a door in the running app: who to log in as, the address to open, the clicks,
and what must exist first. The agent starts every item from here.

Addresses are Appian's defaults under the base URL (atg mcp --base-url, or ATG_BASE_URL);
without one they stay paths to put after your Appian address. A user task needs its process
started first, so its route names the doors that start it; a timer or message start has no
door to open, so its route says how to see it run instead.
"""

from __future__ import annotations

from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas

Route = dict[str, Any]


def base_url(atlas: Atlas) -> str:
    return str(atlas.memo.get("base_url", "")).rstrip("/")


def route(atlas: Atlas, door: dict[str, Any]) -> Route:
    kind, name = door["kind"], door["name"]
    path = (door.get("url") or "").split(" ")[0]
    base = base_url(atlas)
    out: Route = {
        "door": door["id"],
        "log_in_as": log_in_as(door),
        "open": (base + path) if path else "",
        "steps": [],
        "needs": door.get("needs_state", []),
    }
    if path and not base:
        out["note"] = "put your Appian address before the path (atg mcp --base-url sets it)"
    record = (door.get("needs_state") and f" where {' and '.join(door['needs_state'])}") or ""
    steps: list[str] = out["steps"]
    if kind == "site page":
        steps += [f"Open {out['open']}", f'The page "{name}" of site {door["in"]} shows.']
    elif kind == "record list action":
        steps += [f"Open the {door['in']} list: {out['open']}", f'Click "{name}" above the list.']
    elif kind in {"related action", "record view"}:
        steps += [f"Open the {door['in']} list: {out['open']}", f"Open a record{record}."]
        where = "in Related Actions" if kind == "related action" else "as a tab of the record"
        steps.append(f'Open "{name}" {where}.')
    elif kind == "user task":
        first = starters(atlas, door["in_id"])
        steps.append(
            "First make the task exist: start "
            + (" or ".join(f'"{d["name"]}" ({d["kind"]})' for d in first) or "its process")
            + f" ({door['in']}) and go on until it reaches this task."
        )
        steps += [f"Log in as {out['log_in_as']}.", f"Open {out['open']}", f'Open "{name}".']
        out["first"] = [{"door": d["id"], "name": d["name"]} for d in first]
    elif kind == "web API":
        steps.append(f'Call the web API "{name}" (its address is in the Admin Console).')
    else:
        steps.append(_start_note(door))
    return out


def log_in_as(door: dict[str, Any]) -> str:
    """The groups that may both see and use the door, or who else it is for."""
    if door["kind"].endswith("start"):
        return "nobody: it runs on its own"
    seen = {g for gate in door.get("gates", []) for g in gate.get("groups", [])}
    perm = door.get("permission") or {}
    allowed = set(perm.get("groups", [])) if perm.get("found") and not perm["everyone"] else set()
    groups = sorted(seen & allowed if seen and allowed else seen or allowed)
    own = any(g.get("kind") == "own data" for g in door.get("gates", []))
    who = "a member of " + " or ".join(groups) if groups else "any user who can open the app"
    return who + (" who owns the record" if own else "")


def starters(atlas: Atlas, pm: str) -> list[dict[str, Any]]:
    """Doors that start a process (directly or through screens), tasks left out."""
    return [
        d for d in doors.leading_to(atlas, pm) if d["kind"] != "user task" and d["in_id"] != pm
    ][:5]


def _start_note(door: dict[str, Any]) -> str:
    trigger = door.get("trigger", "")
    if trigger == "timer":
        return "It runs on a timer: nothing to click. Check its results after it runs."
    if trigger == "message":
        return "Another process or system starts it with a message: test it from that side."
    return "Nothing in this export starts it: ask the team how it is started."


def for_object(atlas: Atlas, uuid: str) -> Route | None:
    """The route of the first door that leads to an object, if any."""
    first = next(iter(doors.leading_to(atlas, uuid)), None)
    return route(atlas, first) if first else None
