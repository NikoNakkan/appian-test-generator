"""Coverage items and test ideas for approved use cases, per technique:
  scenario  the main scenario and each alternative (paths covering every gateway option once);
            ideas that walk the same steps are merged
  access    one per nearest negative (refused, hidden, someone else's record)
  state     a record in the needed state, and one not in it
Expected results say where they come from. "Configured effects" are what the export says the
app does: they are statically supported, not what the business wants, so every idea also
needs a person's expected business result before it can be trusted as an oracle.
"""

from __future__ import annotations

from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis import review, usecases
from atg.analysis.store import digest

BASIS_EFFECTS = "statically supported: configured effects in the export"
BASIS_ACCESS = (
    "statically supported: gate or role map as configured; enforcement needs a runtime check"
)
NEEDS_PERSON = "business result: needs a person"


def _items(uc: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        {
            "technique": "scenario",
            "covers": p["covers"],
            "steps": p["steps"],
            "expected": p["changes"],
            "basis": [BASIS_EFFECTS, NEEDS_PERSON],
        }
        for p in [uc["main"], *uc["alternatives"]]
    ]
    items += [
        {
            "technique": "access",
            "covers": n,
            "steps": [uc["entry"]["door"]],
            "expected": ["hidden or refused"],
            "basis": [BASIS_ACCESS],
        }
        for n in uc["negatives"]
    ]
    for p in [x for x in uc["preconditions"] if x.endswith('"')]:
        items.append(
            {
                "technique": "state",
                "covers": f"record where {p}",
                "steps": [uc["entry"]["door"]],
                "expected": ["the door works"],
                "basis": [BASIS_EFFECTS],
            }
        )
    return items


def build(atlas: Atlas) -> list[dict[str, Any]]:
    if "test_ideas" in atlas.memo:
        found: list[dict[str, Any]] = atlas.memo["test_ideas"]
        return found
    out = []
    for uc in usecases.build(atlas):
        if uc["status"] != "approved":
            continue
        seen: dict[str, dict[str, Any]] = {}
        for n, item in enumerate(_items(uc)):
            same = digest(item["technique"], item["steps"], item["expected"])
            if same in seen:
                seen[same]["also_covers"].append(item["covers"])
                continue
            idea = {
                "id": f"t:{uc['id']}:{n}",
                "use_case": uc["id"],
                "feature": uc["feature"],
                **item,
                "also_covers": [],
            }
            idea["input_hash"] = digest(uc["input_hash"], item)
            idea["status"] = review.status(atlas, "approve_test", idea["id"], idea["input_hash"])
            seen[same] = idea
        out += list(seen.values())
    atlas.memo["test_ideas"] = out
    return out


def get(atlas: Atlas, test_id: str) -> dict[str, Any] | None:
    return next((t for t in build(atlas) if t["id"] == test_id), None)


def coverage_items(atlas: Atlas) -> dict[str, tuple[int, int]]:
    """technique -> (items covered by an approved idea, items enumerated)."""
    out: dict[str, tuple[int, int]] = {}
    for idea in build(atlas):
        n = 1 + len(idea["also_covers"])
        done, total = out.get(idea["technique"], (0, 0))
        out[idea["technique"]] = (done + (n if idea["status"] == "approved" else 0), total + n)
    return out
