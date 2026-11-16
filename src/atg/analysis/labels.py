"""One accounting label per object, so every object ends somewhere: core (of one draft),
shared (reached from several features), supporting (data, groups, connections), container,
excluded (a person said so), or unreached, with the likely reason. "Unreached" is not "dead":
another app, a name built in a string, or a link reach does not follow may use it.
"""

from __future__ import annotations

from atg.agent import reach
from atg.agent.atlas import Atlas
from atg.analysis import review
from atg.analysis.drafts import build

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


def labels(atlas: Atlas) -> dict[str, tuple[str, str]]:
    """One accounting label per object: (label, reason)."""
    rules = review.constraints(atlas)
    drafts = build(atlas)
    core = {u: d["key"] for d in drafts for u in d["core"]}
    shared = {u for d in drafts for u in d["shared"]}
    reached_any = set().union(*reach.reach(atlas).values()) if drafts else set()
    out: dict[str, tuple[str, str]] = {}
    for u, (t, _) in atlas.objects.items():
        if u in rules["excluded"]:
            out[u] = ("excluded", rules["excluded"][u])
        elif t in CONTAINERS:
            out[u] = ("container", "holds or organises other objects")
        elif u in core:
            out[u] = ("core", f"draft {core[u]}")
        elif u in shared:
            out[u] = ("shared", "reached from several features")
        elif u in reached_any:
            out[u] = ("supporting", "data, groups or connections the features use")
        else:
            out[u] = ("unreached", _why(atlas, u, reached_any))
    return out


def _why(atlas: Atlas, u: str, reached: set[str]) -> str:
    users = atlas.used_by.get(u, [])
    if not users:
        return "nothing in this export uses it: another app, a name in a string, or unused"
    if not set(users) & reached:
        return "only used by other objects no door reaches"
    return "used only through links reach does not follow"


def unreached(atlas: Atlas) -> list[dict[str, str]]:
    return [
        {**atlas.ref(u), "why": why}
        for u, (lab, why) in labels(atlas).items()
        if lab == "unreached"
    ]
