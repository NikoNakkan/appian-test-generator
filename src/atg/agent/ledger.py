"""Runtime findings: what the agent saw in a running app, one row per user and thing seen, and
what is still left to see. Kept apart from static analysis progress (analysis/progress.py):
seeing something at runtime never raises a static measure. A finding that names an environment
needs a current authorisation for it (atg authorise); it may name the static claim it checks.

Results: seen (it is there), matches (it behaves as the map says), differs (it does not: say
how in the note), hidden (not shown to this user), refused (shown but not allowed), broken.
Findings are kept per snapshot, so a new import starts a fresh coverage count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas
from atg.agent.cards import cut

RESULTS = ("seen", "matches", "differs", "hidden", "refused", "broken")


def record(
    atlas: Atlas,
    user: str,
    key: str,
    result: str,
    note: str = "",
    environment: str = "",
    claim: str = "",
) -> dict[str, Any]:
    from atg.analysis import authorise  # the analysis file is opened only when needed

    if environment and authorise.current(atlas, environment) is None:
        return {"error": f"no current authorisation for environment {environment!r}"}
    if result not in RESULTS:
        return {"error": f"result must be one of {', '.join(RESULTS)}"}
    if not user.strip():
        return {"error": "user is required (the test user or persona the agent is logged in as)"}
    with atlas.con:
        atlas.con.execute(
            "INSERT INTO findings (snapshot_id, user, object, result, note, created_at, claim, "
            "environment) VALUES (?,?,?,?,?,?,?,?)",
            (
                atlas.sid,
                user,
                key,
                result,
                note[:2000],
                datetime.now(UTC).isoformat(),
                claim or None,
                environment or None,
            ),
        )
    return {"recorded": {"user": user, "id": key, "result": result}}


def coverage(atlas: Atlas, user: str = "") -> dict[str, Any]:
    rows = atlas.con.execute(
        "SELECT user, object, result, note FROM findings WHERE snapshot_id = ? ORDER BY id",
        (atlas.sid,),
    ).fetchall()
    latest = {(u, o): (r, n) for u, o, r, n in rows if not user or u == user}
    seen_ids = {o for _, o in latest}
    all_doors = doors.doors(atlas)
    unseen = [d for d in all_doors if d["id"] not in seen_ids]
    differs = [
        {"user": u, "id": o, "note": n}
        for (u, o), (r, n) in latest.items()
        if r in {"differs", "broken"}
    ]
    return {
        "user": user or "all users",
        "doors": len(all_doors),
        "doors_seen": len({d["id"] for d in all_doors} & seen_ids),
        "findings": len(latest),
        "unseen": cut([{"id": d["id"], "kind": d["kind"], "name": d["name"]} for d in unseen], 40),
        "unseen_gated": len([d for d in unseen if d["gates"]]),
        "differs_or_broken": cut(differs, 40),
        "users": sorted({u for u, _, _, _ in rows}),
    }
