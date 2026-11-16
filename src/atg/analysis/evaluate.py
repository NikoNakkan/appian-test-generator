"""How close the drafts are to a grouping people made on their own, door by door.

Extended B-cubed (Amigó et al. 2009) works when an item may sit in several groups: for each
door, precision asks how many doors grouped with it truly belong with it, recall how many that
belong with it were grouped with it. Also listed: reference features split over several
drafts (oversplit), drafts mixing several reference features (overmerge), doors the reference
names that the map does not have, and how many decisions people needed (correction effort).
Comparing two runs' drafts the same way gives their stability.
"""

from __future__ import annotations

from typing import Any

Grouping = dict[str, set[str]]  # group name -> door ids


def _member_of(g: Grouping) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name, items in g.items():
        for i in items:
            out.setdefault(i, set()).add(name)
    return out


def bcubed(found: Grouping, truth: Grouping) -> dict[str, float]:
    c, lab = _member_of(found), _member_of(truth)
    items = sorted(set(c) & set(lab))
    if not items:
        return {"precision": 0.0, "recall": 0.0, "f": 0.0}

    def score(e: str, base: dict[str, set[str]]) -> float:
        peers = [x for x in items if base[e] & base[x]]
        return sum(
            min(len(c[e] & c[x]), len(lab[e] & lab[x])) / len(base[e] & base[x]) for x in peers
        ) / len(peers)

    p = sum(score(e, c) for e in items) / len(items)
    r = sum(score(e, lab) for e in items) / len(items)
    return {
        "precision": round(p, 3),
        "recall": round(r, 3),
        "f": round(2 * p * r / (p + r), 3) if p + r else 0.0,
    }


def compare(found: Grouping, truth: Grouping, decisions: int = 0) -> dict[str, Any]:
    c, t = _member_of(found), _member_of(truth)
    known = set(c)
    split = [n for n, ds in truth.items() if len({g for d in ds & known for g in c[d]}) > 1]
    merged = [n for n, ds in found.items() if len({x for d in ds for x in t.get(d, set())}) > 1]
    return {
        **bcubed(found, truth),
        "drafts": len(found),
        "reference_features": len(truth),
        "oversplit": sorted(split),
        "overmerged": sorted(merged),
        "reference_doors_not_in_map": sorted(set().union(*truth.values()) - known) if truth else [],
        "correction_effort": decisions,
    }
