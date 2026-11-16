"""One card per object or door, the same shape for every kind, small enough to read at once.

  id, type, name, what       what it is, in one line
  reached_from               doors whose target leads here
  uses / used_by             links one step out (names, ids to drill into)
  gates                      who may see or do it, with how sure we are
  changes                    what it changes when used
  needs                      inputs it takes
  decisions                  its branches in plain English
  gaps                       what the map cannot tell (outside the export, unparsed, dynamic)
Long lists are cut to LIMIT items with a count of the rest.
"""

from __future__ import annotations

from typing import Any

from atg.agent import doors, process
from atg.agent.atlas import Atlas
from atg.agent.effects import node_effects
from atg.agent.gates import gates_in
from atg.sail import actions
from atg.sail.explain import phrase

LIMIT = 25
Card = dict[str, Any]


def cut(items: list[Any], limit: int = LIMIT) -> list[Any]:
    return items if len(items) <= limit else [*items[:limit], f"... {len(items) - limit} more"]


def card(atlas: Atlas, key: str) -> Card:
    door = doors.by_id(atlas, key)
    if door is not None:
        return {**door, "type": "door", "next": "card(opens.id) for what it opens"}
    if key not in atlas.objects:
        return {"id": key, "error": "not in this export (it may live in another app)"}
    kind, name = atlas.objects[key]
    d = atlas.det(key)
    c: Card = {
        "id": key,
        "type": kind,
        "name": name,
        "what": d.get("description") or "",
        "reached_from": cut([door_ref(x) for x in doors.leading_to(atlas, key)], 10),
        "uses": cut([atlas.ref(u) for u in atlas.uses.get(key, [])]),
        "used_by": cut([atlas.ref(u) for u in atlas.used_by.get(key, [])]),
        "gates": [],
        "changes": [],
        "needs": [f"{i['name']} ({i['type']})" for i in d.get("inputs", [])],
        "decisions": [],
        "gaps": gaps(atlas, key),
    }
    text = atlas.text(key)
    if text:
        c["gates"] = gates_in(atlas, text, "part" if kind == "interface" else "whole")
        c["decisions"] = cut(_decisions(atlas, key), 15)
    if kind == "interface":
        c["changes"] = cut([_action(atlas, a) for a in actions.find(text)], 15)
    elif kind == "processModel":
        _process(atlas, key, c)
    elif kind == "recordType":
        _record(atlas, key, c)
    elif kind == "constant":
        held = [atlas.ref(u) for v in [key] for u in atlas.resolve(v) if u != key]
        c["what"] = (
            c["what"] or f"value: {', '.join(d.get('constant', {}).get('values', []))[:200]}"
        )
        c["stands_for"] = held
    elif kind == "site":
        c["doors"] = [door_ref(x) for x in doors.doors(atlas) if x["in"] == name]
    elif kind == "group":
        c["next"] = "visible_to(id) for what this group can reach"
    return c


def door_ref(d: dict[str, Any]) -> dict[str, Any]:
    gated = [g["says"] for g in d["gates"]]
    return {"id": d["id"], "kind": d["kind"], "name": d["name"], "url": d["url"], "gates": gated}


def _decisions(atlas: Atlas, key: str) -> list[str]:
    seen: dict[str, None] = {}
    for kind, fn, cond in atlas.con.execute(
        "SELECT kind, function, condition FROM branches WHERE snapshot_id = ? AND owner_uuid = ?",
        (atlas.sid, key),
    ):
        if kind in {"if", "match", "null check", "and", "or"} or not seen:
            seen.setdefault(f"{fn}: {phrase(cond, atlas.names) or cond[:120]}", None)
    return list(seen)


def _action(atlas: Atlas, a: actions.Action) -> str:
    parts = [f"starts process {atlas.name(u)}" for u in a.starts]
    parts += [f"writes {atlas.name(u)}" for u in a.writes]
    parts += [f"deletes {atlas.name(u)}" for u in a.deletes]
    parts += [f"opens record action {r.split('/')[-1]}" for r in a.record_actions]
    if a.submits:
        parts.append("submits the form")
    what = ", ".join(parts) or (f"saves {a.saves} value(s)" if a.saves else "no change found")
    return f'{a.kind} "{a.label}": {what}'


def _process(atlas: Atlas, key: str, c: Card) -> None:
    c.update(process.summary(atlas, key))
    c["changes"] = cut(
        list(dict.fromkeys(e for es in node_effects(atlas, key).values() for e in es))
    )
    variables = atlas.det(key).get("variables", [])
    c["needs"] = [f"{v['name']} ({v['type']})" for v in variables if v.get("parameter")]
    c["next"] = "process(id) for test paths that cover every gateway option"


def _record(atlas: Atlas, key: str, c: Card) -> None:
    d = atlas.det(key)
    fields = d.get("fields", [])
    c["fields"] = cut([f["name"] for f in fields], 40)
    c["status_fields"] = [f["name"] for f in fields if _statusish(f["name"])]
    c["source"] = d.get("source", {}).get("table", "")
    c["doors"] = [door_ref(x) for x in doors.doors(atlas) if x["in"] == atlas.name(key)]


def _statusish(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in ("status", "state", "estado", "stage", "phase"))


def gaps(atlas: Atlas, key: str) -> list[str]:
    out = []
    if n := atlas.outside.get(key):
        out.append(f"{n} reference(s) point outside this export: explore them in the app")
    for loc, err in atlas.con.execute(
        "SELECT location, error FROM sail_parse "
        "WHERE snapshot_id = ? AND owner_uuid = ? AND ok = 0",
        (atlas.sid, key),
    ):
        out.append(f"logic in {loc} could not be read ({(err or '').splitlines()[0][:80]})")
    stopped = atlas.con.execute(
        "SELECT truncated FROM path_stats WHERE snapshot_id = ? AND pm_uuid = ?", (atlas.sid, key)
    ).fetchone()
    if stopped and stopped[0]:
        out.append("too many combinations to list them all: use process(id) covering paths")
    return out
