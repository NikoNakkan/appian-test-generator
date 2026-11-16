"""Feature drafts, built by fixed rules from the doors and what they reach, then shaped by
people's decisions. A draft is a proposal until a person approves it, or until it passes every
certainty check (certainty.py) and is auto-accepted, a status counted apart from approvals.

Doors join one draft when they open the same thing, or act on the same record type and share
most of what they reach (not counting shared helpers). A user task joins the draft whose doors
start its process; a timer or message start joins the draft that reaches its process. People
override everything: merge, split and move become must-link / cannot-link rules that every
later build follows. Three groupings are compared (by target, by user type, by record type);
where they disagree the draft says so.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from atg.agent import doors, reach
from atg.agent.atlas import Atlas
from atg.analysis import certainty, review, reviews
from atg.analysis.store import content_hash, digest, open_for

SUPPORTING = frozenset({"recordType", "datatype", "group", "connectedSystem", "dataStore"})
OVERLAP = 0.5


def _record_type(atlas: Atlas, door: dict[str, Any], reached: set[str]) -> str:
    if atlas.type(door.get("in_id", "")) == "recordType":
        return str(door["in_id"])
    rts = sorted(u for u in reached if atlas.type(u) == "recordType")
    return rts[0] if len(rts) == 1 else ""


def actor_key(door: dict[str, Any]) -> str:
    groups = {g for gate in door["gates"] for g in gate.get("groups", [])}
    groups |= set(door.get("permission", {}).get("groups", []))
    if groups:
        return ", ".join(sorted(groups))
    return "anyone (no gate found)" if door["trigger"] == "user" else door["trigger"]


class _Groups:
    def __init__(self, ids: list[str], cannot: set[frozenset[str]]) -> None:
        self.of = {i: i for i in ids}
        self.members = {i: {i} for i in ids}
        self.why: dict[str, list[str]] = {i: [] for i in ids}
        self.cannot = cannot

    def merge(self, a: str, b: str, why: str, force: bool = False) -> None:
        ra, rb = self.of[a], self.of[b]
        if ra == rb:
            return
        blocked = any(
            frozenset((x, y)) in self.cannot for x in self.members[ra] for y in self.members[rb]
        )
        if blocked and not force:
            return
        for m in self.members[rb]:
            self.of[m] = ra
        self.members[ra] |= self.members.pop(rb)
        self.why[ra] += [*self.why.pop(rb), why]


def build(atlas: Atlas) -> list[dict[str, Any]]:
    if "drafts" in atlas.memo:
        built: list[dict[str, Any]] = atlas.memo["drafts"]
        return built
    rules = review.constraints(atlas)
    all_doors = doors.doors(atlas)
    by_id = {d["id"]: d for d in all_doors}
    reached = reach.reach(atlas)
    shared = reach.shared(atlas, rules["shared"])
    g = _Groups(list(by_id), rules["cannot"])
    for a, b in rules["must"]:
        if a in by_id and b in by_id:
            g.merge(a, b, "a person put these together", force=True)
    users = [
        d for d in all_doors if d["kind"] not in {"user task"} and not d["id"].startswith("start:")
    ]
    first: dict[str, str] = {}
    for d in users:
        target = (d["opens"] or {}).get("id", "")
        if target and target in first:
            g.merge(first[target], d["id"], f"both open {atlas.name(target)}")
        first.setdefault(target, d["id"])
    own = {d["id"]: reached[d["id"]] - shared for d in users}
    rt = {d["id"]: _record_type(atlas, d, reached[d["id"]]) for d in users}
    for i, a in enumerate(users):
        for b in users[i + 1 :]:
            if rt[a["id"]] and rt[a["id"]] == rt[b["id"]]:
                inter, union = own[a["id"]] & own[b["id"]], own[a["id"]] | own[b["id"]]
                if union and len(inter) / len(union) >= OVERLAP:
                    g.merge(
                        a["id"],
                        b["id"],
                        f"same record type {atlas.name(rt[a['id']])}, "
                        "and they reach mostly the same objects",
                    )
    for d in all_doors:
        if d["kind"] == "user task" or d["id"].startswith("start:"):
            pm = d["in_id"] if d["kind"] == "user task" else (d["opens"] or {}).get("id", "")
            starts = [s for s in all_doors if s["id"].startswith("start:") and s["id"] != d["id"]]
            host = next((u["id"] for u in [*users, *starts] if pm in reached[u["id"]]), "")
            if host:
                g.merge(
                    host, d["id"], f"{d['name']} runs in a process {by_id[host]['name']} starts"
                )
    out = [
        _draft(atlas, sorted(m), g.why[root], by_id, reached, shared, rules)
        for root, m in g.members.items()
    ]
    reviews.apply(atlas, out, rules["names"])
    unique_names(out, by_id, rules["names"])
    certainty.apply(atlas, out)
    atlas.memo["drafts"] = sorted(out, key=lambda d: d["name"].lower())
    return list(atlas.memo["drafts"])


def unique_names(out: list[dict[str, Any]], by_id: dict[str, Any], given: dict[str, str]) -> None:
    """Drafts named after the same door title ("Create", "Review") get where the door lives,
    then its kind, then a number, until every made-up name differs. A person's name is kept."""
    lead = {
        d["key"]: next((x for x in d["doors"] if x["kind"] != "user task"), d["doors"][0])
        for d in out
    }

    def extra(d: dict[str, Any], step: int) -> str:
        door = lead[d["key"]]
        return str(by_id[door["id"]].get("in") or "") if step == 0 else str(door["kind"])

    for step in (0, 1):
        clash = Counter(d["name"] for d in out)
        for d in out:
            if clash[d["name"]] > 1 and d["key"] not in given and (e := extra(d, step)):
                d["name"] += f" · {e}"
    clash, seen = Counter(d["name"] for d in out), Counter[str]()
    for d in sorted(out, key=lambda d: d["key"]):
        if clash[d["name"]] > 1 and d["key"] not in given:
            seen[d["name"]] += 1
            d["name"] += f" #{seen[d['name']]}"


def _draft(
    atlas: Atlas,
    ids: list[str],
    why: list[str],
    by_id: dict[str, Any],
    reached: dict[str, set[str]],
    shared: set[str],
    rules: dict[str, Any],
) -> dict[str, Any]:
    mine = set().union(*(reached[i] for i in ids))
    others = set().union(*(r for i, r in reached.items() if i not in ids))
    core = sorted(u for u in mine - others - shared if atlas.type(u) not in SUPPORTING)
    key = ids[0]
    lead = next((by_id[i] for i in ids if by_id[i]["kind"] != "user task"), by_id[ids[0]])
    actors = sorted({actor_key(by_id[i]) for i in ids if by_id[i]["kind"] != "user task"})
    rts = sorted({atlas.name(u) for u in _main_record_types(atlas, mine)})
    against = []
    if len(actors) > 1:
        against.append("doors for different user types: " + " | ".join(actors))
    if len(rts) > 1:
        against.append("acts on several record types: " + ", ".join(rts))
    h = digest(ids, [content_hash(atlas, u) for u in core])
    return {
        "key": key,
        "name": rules["names"].get(key)
        or f"{lead['name']}" + (f" ({rts[0]})" if len(rts) == 1 else ""),
        "status": review.status(atlas, "approve", key, h),
        "doors": [{k: by_id[i][k] for k in ("id", "kind", "name", "trigger")} for i in ids],
        "actors": actors,
        "record_types": rts,
        "core": core,
        "shared": sorted(
            (mine & shared) | {u for u in mine & others if atlas.type(u) not in SUPPORTING}
        ),
        "supporting": sorted(u for u in mine if atlas.type(u) in SUPPORTING),
        "why": why or ["one door on its own"],
        "against": against,
        "input_hash": h,
    }


def _main_record_types(atlas: Atlas, mine: set[str]) -> set[str]:
    """Record types reached, minus children of another reached type (claim lines of a claim)."""
    found = {u for u in mine if atlas.type(u) == "recordType"}
    children = {
        r["target"]
        for u in found
        for r in atlas.det(u).get("relationships", [])
        if r.get("kind", "").startswith("ONE_TO")
    }
    return found - children or found


def card(atlas: Atlas, key: str) -> dict[str, Any]:
    d = next(
        (x for x in build(atlas) if x["key"] == key or key in [y["id"] for y in x["doors"]]), None
    )
    if d is None:
        return {"error": f"no draft {key!r}"}
    con = open_for(atlas)
    described = {
        s
        for (s,) in con.execute(
            "SELECT subject FROM items WHERE snapshot_id = ? AND "
            "kind = 'describe_object' AND status IN ('done', 'done-partial')",
            (atlas.sid,),
        )
    }
    subjects = [x["id"] for x in d["doors"]] + d["core"]
    claims = con.execute(
        f"SELECT subject, predicate, value, level FROM claims WHERE snapshot_id = ? AND subject IN "
        f"({','.join('?' * len(subjects))}) ORDER BY id",
        (atlas.sid, *subjects),
    ).fetchall()
    related = sorted(
        {
            x["key"]
            for x in build(atlas)
            if x["key"] != d["key"] and set(x["shared"]) & set(d["shared"])
        }
    )
    return {
        **d,
        "core": [atlas.ref(u) for u in d["core"]],
        "shared": [atlas.ref(u) for u in d["shared"]],
        "supporting": [atlas.ref(u) for u in d["supporting"]],
        "related": related[:10],
        "unexplained": [atlas.name(u) for u in d["core"] if u not in described][:25],
        "claims": [
            {"subject": s, "predicate": p, "value": v, "level": lv} for s, p, v, lv in claims
        ],
    }
