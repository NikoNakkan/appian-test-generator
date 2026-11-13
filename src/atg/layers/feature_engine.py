"""Layer 4 engine: entry points, what each one reaches, and the features they form.

Entry points: site pages and record actions (from Layer 1), web APIs, and then any process no
feature reaches (started by a timer, an event or another app). A feature is one entry target
plus everything reachable from it. Reach expands through screens, rules, decisions,
integrations, processes and constants (a!startProcess often names its process through a
constant); record types and data types are collected but not expanded (every query would
otherwise pull in the whole app), and groups are left to the test-users list.
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass, field

EXPAND = frozenset(
    {"interface", "rule", "decision", "processModel", "integration", "webApi", "constant"}
)
LEAVES = frozenset({"recordType", "datatype", "connectedSystem", "dataStore", "report"})
STANDALONE = "process started outside the app"
CONTAINERS = frozenset(
    {
        "application",
        "folder",
        "rulesFolder",
        "processModelFolder",
        "knowledgeCenter",
        "document",
        "site",
    }
)


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    target: str
    owner: str = ""  # the site or record type that holds it ("" for derived ones)
    description: str = ""


@dataclass
class Feature:
    key: str  # the entry target's UUID: stable across snapshots
    name: str
    entries: list[Entry] = field(default_factory=list)
    members: set[str] = field(default_factory=set)


def entry_points(con: sqlite3.Connection, sid: int) -> list[Entry]:
    found = [
        Entry(k, n, t, o, d)
        for o, k, n, t, d in con.execute(
            "SELECT owner_uuid, kind, name, target, description FROM entry_points "
            "WHERE snapshot_id = ? ORDER BY rowid",
            (sid,),
        )
    ]
    found += [
        Entry("web API", n, u)
        for u, n in con.execute(
            "SELECT uuid, name FROM objects WHERE snapshot_id = ? AND type = 'webApi'", (sid,)
        )
    ]
    return found


def graph(con: sqlite3.Connection, sid: int) -> tuple[dict[str, str], dict[str, set[str]]]:
    types = dict(con.execute("SELECT uuid, type FROM objects WHERE snapshot_id = ?", (sid,)))
    succ: dict[str, set[str]] = {}
    for src, target in con.execute(
        "SELECT DISTINCT source_uuid, target FROM refs WHERE snapshot_id = ? "
        "AND kind NOT IN ('platform', 'self')",
        (sid,),
    ):
        if types.get(src) in EXPAND and types.get(target) in EXPAND | LEAVES:
            succ.setdefault(src, set()).add(target)
    return types, succ


def reach(start: str, types: dict[str, str], succ: dict[str, set[str]]) -> set[str]:
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in succ.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                if types.get(nxt) in EXPAND:
                    queue.append(nxt)
    return seen


def build(con: sqlite3.Connection, sid: int) -> tuple[list[Feature], list[Entry]]:
    """Features (entry points sharing a target become one), plus entries pointing outside."""
    types, succ = graph(con, sid)
    features: dict[str, Feature] = {}
    outside = []
    for e in entry_points(con, sid):
        if e.target not in types:
            outside.append(e)
            continue
        f = features.setdefault(e.target, Feature(e.target, e.name or e.target))
        f.entries.append(e)
    for f in features.values():
        f.members = reach(f.key, types, succ)
        titles = list(dict.fromkeys(e.name for e in f.entries if e.name))
        if len(titles) > 1:  # e.g. "New Employee" and "Update Employee" start the same process
            f.name = " / ".join(titles)
    _add_standalone(features, types, succ, names(con, sid))
    return sorted(features.values(), key=lambda f: f.name.lower()), outside


def names(con: sqlite3.Connection, sid: int) -> dict[str, str]:
    return dict(con.execute("SELECT uuid, name FROM objects WHERE snapshot_id = ?", (sid,)))


def _add_standalone(
    features: dict[str, Feature],
    types: dict[str, str],
    succ: dict[str, set[str]],
    object_names: dict[str, str],
) -> None:
    """Processes no feature reaches become entry points, except ones another of them starts."""
    covered = set().union(*(f.members for f in features.values())) if features else set()
    loose = {u for u, t in types.items() if t == "processModel" and u not in covered}
    reached = {u: reach(u, types, succ) for u in loose}
    started_by_other = {m for u, r in reached.items() for m in r if m != u}
    roots = sorted(loose - started_by_other) or sorted(loose)[:1]
    for u in roots:
        f = Feature(u, object_names.get(u, u), [Entry(STANDALONE, object_names.get(u, u), u)])
        f.members = reached[u]
        features[u] = f
    if loose - set().union(*(features[u].members for u in roots), set()):
        _add_standalone(features, types, succ, object_names)  # cycles among loose processes
