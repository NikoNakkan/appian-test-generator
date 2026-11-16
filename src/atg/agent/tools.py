"""The tools an exploring agent calls. Every tool returns a small JSON object.

Start with overview(), then find() on what you see (a URL or a title), card() on a hit, and
follow uses / used_by / reached_from. To work through the app: resume(), then next_item() and
submit() until nothing is left; progress() shows the honest counts. Record what you saw in a
running app with record(); coverage() says what is left. Ids are object UUIDs or door ids
(page:..., action:..., view:..., task:..., api:..., start:...).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from atg.agent import cards, doors, find, ledger, process, who, worktools
from atg.agent.atlas import Atlas

Tool = worktools.Tool


def _overview(atlas: Atlas, _: dict[str, Any]) -> dict[str, Any]:
    all_doors = doors.doors(atlas)
    return {
        "app": [n for t, n in atlas.objects.values() if t == "application"],
        "objects": dict(Counter(t for t, _ in atlas.objects.values()).most_common()),
        "doors": dict(Counter(d["kind"] for d in all_doors)),
        "doors_with_a_gate": sum(1 for d in all_doors if d["gates"]),
        "groups": sorted(n for t, n in atlas.objects.values() if t == "group"),
        "objects_pointing_outside": len(atlas.outside),
        "how_to_start": __doc__.split("\n\n")[1].replace("\n", " ") if __doc__ else "",
    }


def _neighbours(atlas: Atlas, a: dict[str, Any]) -> dict[str, Any]:
    key, way, kind = a["id"], a.get("direction", "both"), a.get("type", "")
    out: dict[str, Any] = {"id": key, "name": atlas.name(key)}
    for d in ("uses", "used_by"):
        if way in (d, "both"):
            links = getattr(atlas, d).get(key, [])
            out[d] = cards.cut(
                [atlas.ref(u) for u in links if not kind or atlas.type(u) == kind], 60
            )
    return out


def _process(atlas: Atlas, a: dict[str, Any]) -> dict[str, Any]:
    key = a["id"]
    if atlas.type(key) != "processModel":
        return {"error": f"{key} is not a process model in this export"}
    return {
        "id": key,
        "name": atlas.name(key),
        **process.summary(atlas, key),
        **process.covering_paths(atlas, key),
    }


def _doors(atlas: Atlas, a: dict[str, Any]) -> dict[str, Any]:
    kind = a.get("kind", "")
    found = [cards.door_ref(d) for d in doors.doors(atlas) if not kind or d["kind"] == kind]
    return {"doors": cards.cut(found, 80)}


TOOLS = [
    Tool("overview", "The app at a glance: counts, doors, groups. Call first.", {}, _overview),
    Tool(
        "doors",
        "Every way in (site pages, record actions, record views, user tasks, web APIs) "
        "with URL and gates.",
        {"kind?": "only this kind, e.g. 'site page'"},
        _doors,
    ),
    Tool(
        "find",
        "Look up what you see: a URL, a page or action title, a label, a name.",
        {"query": "URL or text", "kind?": "only this type or door kind"},
        lambda at, a: find.find(at, a["query"], a.get("kind", "")),
    ),
    Tool(
        "card",
        "Everything about one object or door: uses, used by, gates, changes, decisions, gaps.",
        {"id": "object UUID or door id"},
        lambda at, a: cards.card(at, a["id"]),
    ),
    Tool(
        "neighbours",
        "Links one step out from an object.",
        {"id": "object UUID", "direction?": "uses, used_by or both", "type?": "object type"},
        _neighbours,
    ),
    Tool(
        "process",
        "A process: tasks, and test paths that cover every gateway option once, with "
        "what each path changes.",
        {"id": "process model UUID"},
        _process,
    ),
    Tool(
        "who",
        "Who may reach an object or door, and through which doors.",
        {"id": "object UUID or door id"},
        lambda at, a: who.who(at, a["id"]),
    ),
    Tool(
        "visible_to",
        "What one group can reach, and what does not depend on groups.",
        {"group": "group name or UUID"},
        lambda at, a: who.visible_to(at, a["group"]),
    ),
    Tool(
        "record",
        "Write down what you saw as one user: " + ", ".join(ledger.RESULTS) + ".",
        {
            "user": "test user or persona",
            "id": "object UUID or door id",
            "result": "one of " + ", ".join(ledger.RESULTS),
            "note?": "what you saw",
            "environment?": "authorised environment name",
            "claim?": "id of the claim checked",
        },
        lambda at, a: ledger.record(
            at,
            a["user"],
            a["id"],
            a["result"],
            a.get("note", ""),
            a.get("environment", ""),
            str(a.get("claim", "")),
        ),
    ),
    Tool(
        "coverage",
        "What is seen, what is left, what differed (for one user or all).",
        {"user?": "test user or persona"},
        lambda at, a: ledger.coverage(at, a.get("user", "")),
    ),
    *worktools.TOOLS,
]
BY_NAME = {t.name: t for t in TOOLS}


def call(atlas: Atlas, name: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = BY_NAME.get(name)
    if tool is None:
        return {"error": f"no tool {name!r}; tools: {', '.join(BY_NAME)}"}
    missing = [p for p in tool.params if not p.endswith("?") and not args.get(p)]
    if missing:
        return {"error": f"{name} needs: {', '.join(missing)}"}
    return tool.run(atlas, args)


def schema(tool: Tool) -> dict[str, Any]:
    props = {p.rstrip("?"): {"type": "string", "description": d} for p, d in tool.params.items()}
    required = [p for p in tool.params if not p.endswith("?")]
    return {"type": "object", "properties": props, "required": required}
