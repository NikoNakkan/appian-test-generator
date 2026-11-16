"""When a feature draft is certain enough to accept without a person, judged by evidence code
can count, never by the model's own confidence (which research shows is overconfident).

A draft is auto-accepted when every check passes:
  1 groupings agree   one user type, at most one main record type
  2 no doubts         nothing against it, and no door opens something shared
  3 evidence          every door assessed (done, not partial) and every core object described
  4 runs agree        RUNS separate challenge passes re-checked it and said it holds
  5 nothing open      no blocked item and no open question about its doors or core
  6 small             at most MAX_DOORS doors (big drafts are where mistakes hide)
Auto-accepted is its own status, counted apart from people's approvals. A person can still
approve, split, merge or reject it ("reject" means: a person must look). Any change underneath
(a new import, a merge) changes the draft's inputs, and it drops back to draft.
"""

from __future__ import annotations

from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis import review
from atg.analysis.store import open_for

MAX_DOORS = 5
RUNS = 2
PREVIEW = 8  # characters of the draft's input hash in challenge item ids


def challenge_ids(d: dict[str, Any]) -> list[str]:
    return [f"challenge:{d['key']}:{d['input_hash'][:PREVIEW]}#{n}" for n in range(1, RUNS + 1)]


def _facts(atlas: Atlas) -> dict[str, Any]:
    con = open_for(atlas)
    status = {
        (k, s): st
        for k, s, st in con.execute(
            "SELECT kind, subject, status FROM items WHERE snapshot_id = ?", (atlas.sid,)
        )
    }
    by_id = dict(con.execute("SELECT id, status FROM items WHERE snapshot_id = ?", (atlas.sid,)))
    verdicts: dict[str, list[str]] = {}
    for item, value in con.execute(
        "SELECT item_id, value FROM claims WHERE snapshot_id = ? AND predicate = 'boundary_holds'",
        (atlas.sid,),
    ):
        verdicts.setdefault(item, []).append(str(value).strip().lower())
    asked = {
        s
        for (s,) in con.execute(
            "SELECT subject FROM questions WHERE snapshot_id = ? AND status = 'open'", (atlas.sid,)
        )
    }
    return {"status": status, "by_id": by_id, "verdicts": verdicts, "asked": asked}


def checks(atlas: Atlas, d: dict[str, Any], f: dict[str, Any]) -> list[dict[str, Any]]:
    st = f["status"]
    doors = [x["id"] for x in d["doors"]]
    users = [x["id"] for x in d["doors"] if x["kind"] != "user task"]
    shared_targets = [x for x in users if _opens(atlas, x) in set(d["shared"])]
    unassessed = [x for x in users if st.get(("assess_entry", x)) != "done"]
    undescribed = [u for u in d["core"] if st.get(("describe_object", u)) != "done"]
    stuck = [
        s
        for s in doors + d["core"]
        if s in f["asked"]
        or "blocked" in {st.get(("assess_entry", s)), st.get(("describe_object", s))}
        or "needs-human" in {st.get(("assess_entry", s)), st.get(("describe_object", s))}
    ]
    runs = [(f["by_id"].get(i), f["verdicts"].get(i, [])) for i in challenge_ids(d)]
    held = sum(1 for s, v in runs if s == "done" and v and all(x == "yes" for x in v))
    said_no = any("no" in v for _, v in runs)
    studied = not unassessed and not undescribed
    who, records = ", ".join(d["actors"]) or "nobody found", ", ".join(d["record_types"])
    return [
        _c(
            "groupings agree",
            len(d["actors"]) <= 1 and len(d["record_types"]) <= 1,
            "One kind of user and one main record",
            f"Used by: {who}. Works on: {records or 'no record type'}.",
            "It mixes different users or records: consider splitting it (Split out on a door).",
        ),
        _c(
            "no doubts",
            not d["against"] and not shared_targets,
            "Nothing speaks against it",
            "; ".join(
                d["against"]
                + [
                    f"{atlas.name(_opens(atlas, x)) or x} is also used by other drafts"
                    for x in shared_targets
                ]
            )
            or "No doubts found.",
            "Read the doubts; split the draft or mark the object as shared if they are right.",
        ),
        _c(
            "evidence",
            studied,
            "The agent has studied it",
            "The agent has looked at every way in and every object of its own."
            if studied
            else _unstudied(len(unassessed), len(undescribed)),
            "Run the draft reviewer on this draft (next_item with draft=its key).",
        ),
        _c(
            "runs agree",
            held == RUNS and not said_no,
            "Double-checked by two separate runs",
            "A re-check said this is not one feature."
            if said_no
            else "Both re-checks confirmed it."
            if held == RUNS
            else f"{held} of {RUNS} re-checks done. They start once the agent has studied it."
            if not studied
            else f"{held} of {RUNS} re-checks done.",
            "A person should look: open the doors and approve, split or reject."
            if said_no
            else "Let the agent go on: a separate run re-checks the draft twice.",
        ),
        _c(
            "nothing open",
            not stuck,
            "No open questions",
            "Waiting on: " + ", ".join(atlas.name(s) or s for s in stuck[:5])
            if stuck
            else "Nothing is waiting for an answer.",
            "Answer the agent's questions in the Questions tab.",
        ),
        _c(
            "small",
            len(doors) <= MAX_DOORS,
            "Small enough to trust",
            f"{_n(len(doors), 'way in', 'ways in')} "
            f"(at most {MAX_DOORS} for automatic acceptance).",
            "Big drafts always need a person: approve it or split it.",
        ),
    ]


def _unstudied(doors: int, objects: int) -> str:
    parts = []
    if doors:
        parts.append(f"{_n(doors, 'way in', 'ways in')} (page, action, task)")
    if objects:
        parts.append(f"{_n(objects, 'object', 'objects')} of its own (screen, process, rule)")
    return "The agent has not yet looked at " + " and ".join(parts) + "."


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _c(name: str, ok: bool, label: str, why: str, next_step: str = "") -> dict[str, Any]:
    """name is the stable key; label, why and next are what a person reads."""
    return {"check": name, "ok": ok, "label": label, "why": why, "next": "" if ok else next_step}


def _opens(atlas: Atlas, door_id: str) -> str:
    from atg.agent import doors

    d = doors.by_id(atlas, door_id) or {}
    return str((d.get("opens") or {}).get("id", ""))


def apply(atlas: Atlas, drafts: list[dict[str, Any]]) -> None:
    """Add each draft's checks; mark the ones that pass every check as auto-accepted."""
    f = _facts(atlas)
    for d in drafts:
        d["certainty"] = checks(atlas, d, f)
        rejected = review.status(atlas, "reject", d["key"], d["input_hash"]) == "approved"
        if rejected:
            d["certainty"].append(
                _c(
                    "not rejected",
                    False,
                    "Not sent back by a person",
                    "A person asked to look at it again.",
                    "Approve, split or merge it when you have looked.",
                )
            )
        if d["status"] == "draft" and all(c["ok"] for c in d["certainty"]):
            d["status"] = "auto-accepted"


def ready_for_challenge(d: dict[str, Any]) -> bool:
    """Every check but 'runs agree' passes: worth spending challenge passes on."""
    return d["status"] == "draft" and all(
        c["ok"] for c in d.get("certainty", []) if c["check"] != "runs agree"
    )
