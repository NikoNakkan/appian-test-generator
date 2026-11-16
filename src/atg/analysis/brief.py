"""Everything a reviewer needs about one feature draft, in one answer: what a person sees
(screens with their field and button labels, texts), what happens (processes, tasks and who
gets them, what they write and which statuses they set), the data (record types and fields),
the rules with their descriptions, who may use each door, the drafts it overlaps, the work
still open on it, and how the app names things. Lists are cut; ids lead to card() for more.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from atg.agent import cards, process
from atg.agent.atlas import Atlas
from atg.agent.effects import node_effects
from atg.analysis import drafts, queue
from atg.analysis.store import open_for
from atg.sail import actions, fields

_TEXT = re.compile(r'"([^"\\#\n]{3,80})"')
_SEEN_TYPES = {"interface", "processModel", "recordType"}


def brief(atlas: Atlas, key: str) -> dict[str, Any]:
    queue.seed(atlas)  # so the open work is listed even before the first next_item
    card = drafts.card(atlas, key)
    if "error" in card:
        return card
    raw = next(d for d in drafts.build(atlas) if d["key"] == card["key"])
    mine = [*raw["core"], *raw["shared"]]
    by_type: dict[str, list[str]] = {}
    for u in mine:
        by_type.setdefault(atlas.type(u), []).append(u)
    return {
        "draft": {k: card[k] for k in ("key", "name", "status", "why", "against", "actors")},
        "certainty": [c for c in card.get("certainty", []) if not c["ok"]],
        "doors": [_door(atlas, x["id"]) for x in raw["doors"]],
        "screens": cards.cut([_screen(atlas, u) for u in by_type.get("interface", [])], 12),
        "processes": cards.cut([_process(atlas, u) for u in by_type.get("processModel", [])], 8),
        "records": [_record(atlas, u) for u in by_type.get("recordType", [])][:6],
        "rules_and_other": cards.cut(
            [
                {**atlas.ref(u), "what": atlas.det(u).get("description", "")[:200]}
                for u in mine
                if atlas.type(u) not in _SEEN_TYPES
            ],
            30,
        ),
        "shared_with_other_drafts": [atlas.name(u) for u in raw["shared"]][:20],
        "related_drafts": _related(atlas, raw),
        "unfinished": unfinished(atlas, raw),
        "earlier_claims": cards.cut(card["claims"], 30),
        "naming": naming(atlas),
    }


def _door(atlas: Atlas, door_id: str) -> dict[str, Any]:
    from atg.agent import doors

    d = doors.by_id(atlas, door_id) or {}
    return {
        **cards.door_ref(d),
        "in": d.get("in", ""),
        "opens": (d.get("opens") or {}).get("name", ""),
        "permission": d.get("permission", ""),
    }


def _screen(atlas: Atlas, ui: str) -> dict[str, Any]:
    text = atlas.text(ui)
    found, _ = fields.find(text)
    return {
        **atlas.ref(ui),
        "what": atlas.det(ui).get("description", "")[:200],
        "fields": cards.cut([f"{f.label or '(no label)'} ({f.kind})" for f in found], 20),
        "buttons": cards.cut([cards.action_text(atlas, a) for a in actions.find(text)], 10),
        "texts": cards.cut(list(dict.fromkeys(_TEXT.findall(text))), 15),
    }


def _process(atlas: Atlas, pm: str) -> dict[str, Any]:
    s = process.summary(atlas, pm)
    effects = list(dict.fromkeys(e for es in node_effects(atlas, pm).values() for e in es))
    return {
        **atlas.ref(pm),
        "what": atlas.det(pm).get("description", "")[:200],
        "tasks": cards.cut(s["tasks"], 12),
        "changes": cards.cut(effects, 12),
    }


def _record(atlas: Atlas, rt: str) -> dict[str, Any]:
    c = cards.card(atlas, rt)
    return {
        **atlas.ref(rt),
        "what": c["what"][:200],
        "fields": c.get("fields", []),
        "status_fields": c.get("status_fields", []),
    }


def _related(atlas: Atlas, raw: dict[str, Any]) -> list[dict[str, Any]]:
    mine = set(raw["core"]) | set(raw["shared"])
    out = []
    for d in drafts.build(atlas):
        common = mine & (set(d["core"]) | set(d["shared"]))
        if d["key"] != raw["key"] and common:
            out.append(
                {
                    "key": d["key"],
                    "name": d["name"],
                    "summary": d.get("summary", ""),
                    "same_record_type": bool(set(d["record_types"]) & set(raw["record_types"])),
                    "in_common": [atlas.name(u) for u in sorted(common)][:5],
                    "count": len(common),
                }
            )
    return sorted(out, key=lambda r: -int(r["count"]))[:10]


def unfinished(atlas: Atlas, raw: dict[str, Any]) -> dict[str, Any]:
    subjects = [x["id"] for x in raw["doors"]] + raw["core"]
    con = open_for(atlas)
    marks = ",".join("?" * len(subjects))
    items = con.execute(
        f"SELECT id, kind, status FROM items WHERE snapshot_id = ? AND subject IN ({marks}) "
        "AND status NOT IN ('done') ORDER BY id",
        (atlas.sid, *subjects),
    ).fetchall()
    asked = con.execute(
        f"SELECT id, text, status FROM questions WHERE snapshot_id = ? AND subject IN ({marks})",
        (atlas.sid, *subjects),
    ).fetchall()
    return {
        "items": cards.cut([{"item": i, "kind": k, "status": s} for i, k, s in items], 40),
        "questions": [{"id": i, "text": t, "status": s} for i, t, s in asked],
    }


def naming(atlas: Atlas) -> list[dict[str, Any]]:
    """Name prefixes the app uses, with the object types behind them (OP_X_RT_ -> recordType),
    so the reviewer can read names like OP_X_P_EnvioFirma as "process: envio firma"."""
    if "naming" in atlas.memo:
        kept: list[dict[str, Any]] = atlas.memo["naming"]
        return kept
    seen: dict[str, Counter[str]] = {}
    for t, name in atlas.objects.values():
        parts = name.split("_")
        for n in range(1, min(len(parts), 4)):
            seen.setdefault("_".join(parts[:n]) + "_", Counter())[t] += 1
    rows: list[dict[str, Any]] = [
        {"prefix": p, "count": sum(c.values()), "types": dict(c.most_common(3))}
        for p, c in seen.items()
        if sum(c.values()) >= 3
    ]
    rows.sort(key=lambda r: (-len(r["prefix"]), -int(r["count"])))
    atlas.memo["naming"] = rows[:25]
    return list(atlas.memo["naming"])
