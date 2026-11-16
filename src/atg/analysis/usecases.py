"""Use cases for approved features only: one per goal (one per door a person or system starts
from), never one per path. Paths become the main scenario and its alternatives; access, owner
and state conditions become nearest negatives (who or what should be refused). A user task
given to someone other than the starter is its own use case (a hand-off).

Labels: the goal comes from the door title unless the agent stated one (actor_goal claim);
preconditions are as configured; nothing here says what the business wants until a person
approves the use case.
"""

from __future__ import annotations

from typing import Any

from atg.agent import cards, doors, process
from atg.agent.atlas import Atlas
from atg.analysis import drafts, review
from atg.analysis.store import digest, open_for


def negatives(door: dict[str, Any]) -> list[str]:
    out = []
    for g in door["gates"]:
        if g["kind"] == "group":
            out.append(f"someone not in {' or '.join(g['groups']) or 'that group'} does not see it")
        elif g["kind"] == "own data":
            out.append("another user's record is not shown or changeable")
        elif g["kind"] == "profile":
            out.append("a user whose profile does not match is treated differently")
        elif g["kind"] == "assigned":
            out.append("someone else does not get the task")
    perm = door.get("permission", {})
    if perm.get("found") and not perm.get("everyone"):
        out.append(f"someone outside {', '.join(perm['groups']) or 'every group'} is refused")
    out += [f"a record where it is not true that {p}" for p in door.get("needs_state", [])]
    if door["trigger"] == "api":
        out.append("a caller without valid credentials is refused")
    return out


def _goal(atlas: Atlas, door: dict[str, Any]) -> tuple[str, str]:
    row = (
        open_for(atlas)
        .execute(
            "SELECT value FROM claims WHERE snapshot_id = ? AND subject = ? AND predicate = "
            "'actor_goal' ORDER BY id DESC LIMIT 1",
            (atlas.sid, door["id"]),
        )
        .fetchone()
    )
    return (str(row[0]), "inferred by the agent") if row else (door["name"], "from the door title")


def _flow(atlas: Atlas, door: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target = (door["opens"] or {}).get("id", "")
    pm = door["in_id"] if door["kind"] == "user task" else target
    if atlas.type(pm) == "processModel":
        paths = process.covering_paths(atlas, pm)["paths"]
        if paths:
            return paths[0], paths[1:]
    screen = cards.card(atlas, target) if target in atlas.objects else {}
    return {
        "covers": "the screen",
        "steps": [atlas.name(target)],
        "changes": screen.get("changes", []),
    }, []


def build(atlas: Atlas) -> list[dict[str, Any]]:
    if "use_cases" in atlas.memo:
        found: list[dict[str, Any]] = atlas.memo["use_cases"]
        return found
    out = []
    for draft in drafts.build(atlas):
        if draft["status"] != "approved":
            continue
        starters = {drafts.actor_key(d) for d in _doors(atlas, draft) if d["kind"] != "user task"}
        for door in _doors(atlas, draft):
            if door["kind"] == "user task" and drafts.actor_key(door) in starters:
                continue  # a step of the starter's own use case
            goal, goal_from = _goal(atlas, door)
            main, alts = _flow(atlas, door)
            uc = {
                "id": f"uc:{door['id']}",
                "feature": draft["key"],
                "goal": goal,
                "goal_from": goal_from,
                "actor": drafts.actor_key(door),
                "trigger": door["trigger"],
                "entry": {"door": door["id"], "url": door["url"]},
                "preconditions": [g["says"] + f" ({g['guard']})" for g in door["gates"]]
                + ([door["permission"]["says"]] if door["permission"].get("found") else [])
                + door["needs_state"],
                "main": main,
                "alternatives": alts,
                "negatives": negatives(door),
                "level": "statically supported structure; business intent not confirmed",
            }
            uc["input_hash"] = digest(draft["input_hash"], uc["main"], uc["preconditions"])
            uc["status"] = review.status(atlas, "approve_use_case", uc["id"], uc["input_hash"])
            out.append(uc)
    atlas.memo["use_cases"] = out
    return out


def _doors(atlas: Atlas, draft: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for x in draft["doors"] if (d := doors.by_id(atlas, x["id"])) is not None]


def get(atlas: Atlas, uc_id: str) -> dict[str, Any] | None:
    return next((u for u in build(atlas) if u["id"] == uc_id), None)
