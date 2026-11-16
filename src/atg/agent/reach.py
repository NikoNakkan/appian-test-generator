"""Which objects each door reaches, how many doors reach each object, and which are shared.

Reach follows "uses" links down from what a door opens, through screens, rules, decisions,
processes, integrations, web APIs and constants; record types, data types and groups are
collected but not followed (otherwise every query reaches the whole app). Everything here is
"may reach": static links over-approximate what a person actually uses.

An object is shared when more doors reach it than the threshold for its type: the larger of
MIN_SHARED and the 90th percentile of fan-in among objects of that type. A person can promote
or demote any object (review decisions), which overrides the threshold.
"""

from __future__ import annotations

from collections import deque

from atg.agent import doors
from atg.agent.atlas import Atlas
from atg.layers.feature_engine import EXPAND

MIN_SHARED = 3
SHAREABLE = frozenset({"interface", "rule", "decision", "constant", "processModel", "integration"})


def _down(atlas: Atlas, start: str) -> set[str]:
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in atlas.uses.get(queue.popleft(), []):
            if nxt not in seen:
                seen.add(nxt)
                if atlas.type(nxt) in EXPAND:
                    queue.append(nxt)
    return seen


def reach(atlas: Atlas) -> dict[str, set[str]]:
    if "reach" not in atlas.memo:
        atlas.memo["reach"] = {
            d["id"]: _down(atlas, d["opens"]["id"])
            if d["opens"] and d["opens"]["type"] != "outside"
            else set()
            for d in doors.doors(atlas)
        }
    out: dict[str, set[str]] = atlas.memo["reach"]
    return out


def fan_in(atlas: Atlas) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reached in reach(atlas).values():
        for u in reached:
            counts[u] = counts.get(u, 0) + 1
    return counts


def thresholds(atlas: Atlas) -> dict[str, int]:
    by_type: dict[str, list[int]] = {}
    for u, n in fan_in(atlas).items():
        by_type.setdefault(atlas.type(u), []).append(n)
    out = {}
    for t, values in by_type.items():
        values.sort()
        out[t] = max(MIN_SHARED, values[int(0.9 * (len(values) - 1))])
    return out


def shared(atlas: Atlas, forced: dict[str, bool] | None = None) -> set[str]:
    """forced: object -> True (a person says shared) / False (a person says not shared)."""
    limits, counts = thresholds(atlas), fan_in(atlas)
    out = {
        u
        for u, n in counts.items()
        if atlas.type(u) in SHAREABLE and n >= limits.get(atlas.type(u), MIN_SHARED)
    }
    for u, is_shared in (forced or {}).items():
        (out.add if is_shared else out.discard)(u)
    return out
