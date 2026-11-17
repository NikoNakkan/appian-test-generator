"""Which tests to run after a change: one verdict per test path, rule and feature.

new (did not exist before), retire (gone), redesign (its own logic changed),
rerun (something it relies on changed) or skip. Built on regression.impacts().
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from atg import pathdb
from atg.regression.impact import Impact, impacts, node_fingerprints, objects_of


@dataclass
class Verdict:
    kind: str  # path, rule, feature
    owner: str  # process / object / feature name
    ref: str  # uuid or feature key
    item: str  # "path 3", rule name, feature name
    verdict: str  # new, retire, redesign, rerun, skip
    reasons: list[str] = field(default_factory=list)


def _paths(con: sqlite3.Connection, sid: int, pm: str) -> dict[str, tuple[int, list[int]]]:
    """Path signature (its steps and choices) -> (path number, steps)."""
    out = {}
    for p in pathdb.read(con, sid, pm):
        choice = [(d["gateway"], d["to"], d["rule"]) for d in p.decisions]
        out[json.dumps([p.steps, choice])] = (p.no, p.steps)
    return out


def path_verdicts(
    con: sqlite3.Connection, base: int, head: int, impacted: dict[str, Impact]
) -> list[Verdict]:
    names = {u: n for u, (_, n, _) in objects_of(con, head).items()}
    old_names = {u: n for u, (_, n, _) in objects_of(con, base).items()}
    pms = _pm_set(con, head) | _pm_set(con, base)
    hot = {u for u, i in impacted.items() if i.status != "added"}
    out: list[Verdict] = []
    for pm in sorted(pms, key=lambda u: names.get(u, old_names.get(u, u))):
        name = names.get(pm, old_names.get(pm, pm))
        old_paths, new_paths = _paths(con, base, pm), _paths(con, head, pm)
        old_nodes, new_nodes = node_fingerprints(con, base, pm), node_fingerprints(con, head, pm)
        labels = dict(
            con.execute(
                "SELECT gui_id, label FROM nodes WHERE snapshot_id = ? AND pm_uuid = ?", (head, pm)
            )
        )
        for sig, (no, steps) in new_paths.items():
            if sig not in old_paths:
                out.append(Verdict("path", name, pm, f"path {no}", "new", ["route did not exist"]))
                continue
            reasons = []
            for gui in dict.fromkeys(steps):
                fp, refs = new_nodes.get(gui, ("", set()))
                label = labels.get(gui) or f"node {gui}"
                if old_nodes.get(gui, ("",))[0] != fp:
                    reasons.append(f"node '{label}' changed")
                for r in sorted(refs & hot):
                    reasons.append(f"node '{label}' uses {impacted[r].name} ({impacted[r].status})")
            out.append(
                Verdict(
                    "path",
                    name,
                    pm,
                    f"path {no}",
                    "rerun" if reasons else "skip",
                    list(dict.fromkeys(reasons))[:5],
                )
            )
        for sig, (no, _) in old_paths.items():
            if sig not in new_paths:
                out.append(Verdict("path", name, pm, f"old path {no}", "retire", ["route is gone"]))
    return out


def _pm_set(con: sqlite3.Connection, sid: int) -> set[str]:
    return {
        u
        for (u,) in con.execute(
            "SELECT uuid FROM objects WHERE snapshot_id = ? AND type = 'processModel'", (sid,)
        )
    }


def rule_verdicts(con: sqlite3.Connection, head: int, impacted: dict[str, Impact]) -> list[Verdict]:
    """Objects with decision points of their own (rules, interfaces, decisions)."""
    out = []
    for owner, kind, name, count in con.execute(
        "SELECT b.owner_uuid, o.type, o.name, COUNT(*) FROM branches b JOIN objects o "
        "ON o.uuid = b.owner_uuid AND o.snapshot_id = b.snapshot_id WHERE b.snapshot_id = ? "
        "AND b.location = 'definition' GROUP BY b.owner_uuid",
        (head,),
    ):
        i = impacted.get(owner)
        verdict = {"added": "new", "changed": "redesign", "affected": "rerun"}.get(
            i.status if i else "", "skip"
        )
        reasons = (
            [f"its code changed ({count} decision points)"]
            if verdict == "redesign"
            else ([f"uses {' → '.join(i.via)}"] if i and i.status == "affected" else [])
        )
        out.append(Verdict("rule", kind, owner, name, verdict, reasons))
    return out


def feature_verdicts(
    con: sqlite3.Connection, base: int, head: int, impacted: dict[str, Impact]
) -> list[Verdict]:
    def features(sid: int) -> dict[str, tuple[str, set[str]]]:
        out: dict[str, tuple[str, set[str]]] = {}
        names = dict(con.execute("SELECT key, name FROM features WHERE snapshot_id = ?", (sid,)))
        for key, uuid in con.execute(
            "SELECT key, uuid FROM feature_members WHERE snapshot_id = ?", (sid,)
        ):
            out.setdefault(key, (names.get(key, key), set()))[1].add(uuid)
        return out

    old, new = features(base), features(head)
    out = []
    for key, (name, members) in sorted(new.items(), key=lambda kv: kv[1][0]):
        if key not in old:
            out.append(Verdict("feature", name, key, name, "new", ["new entry point"]))
            continue
        hit = [impacted[m] for m in members if m in impacted]
        hit += [impacted[m] for m in old[key][1] - members if m in impacted]  # members removed
        reasons = [f"{i.name} {i.status}" for i in sorted(hit, key=lambda i: i.status != "changed")]
        out.append(Verdict("feature", name, key, name, "rerun" if hit else "skip", reasons[:5]))
    out += [
        Verdict("feature", n, k, n, "retire", ["entry point is gone"])
        for k, (n, _) in old.items()
        if k not in new
    ]
    return out


def report(con: sqlite3.Connection, base: int, head: int) -> dict[str, Any]:
    impacted = impacts(con, base, head)
    verdicts = (
        path_verdicts(con, base, head, impacted)
        + rule_verdicts(con, head, impacted)
        + feature_verdicts(con, base, head, impacted)
    )
    summary: dict[str, dict[str, int]] = {}
    for v in verdicts:
        summary.setdefault(v.kind, {}).setdefault(v.verdict, 0)
        summary[v.kind][v.verdict] += 1
    return {
        "base": base,
        "head": head,
        "changes": [vars(i) for i in impacted.values() if i.status != "affected"],
        "affected": [vars(i) for i in impacted.values() if i.status == "affected"],
        "summary": summary,
        "verdicts": [vars(v) for v in verdicts if v.verdict != "skip"],
        "skipped": {k: s.get("skip", 0) for k, s in summary.items()},
    }
