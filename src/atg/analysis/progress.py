"""The ten progress measures, each with its numerator, denominator, counting rule and the list
behind it, plus measurement health. No blended percentage: each measure counts one kind of
thing, and what it supports saying is printed with it.
"""

from __future__ import annotations

from typing import Any

from atg.agent import census, doors
from atg.agent.atlas import Atlas
from atg.analysis import drafts, labels, queue, testideas, usecases
from atg.analysis.store import open_for


def _m(
    name: str, n: int | None, t: int | None, rule: str, claim: str, **extra: Any
) -> dict[str, Any]:
    return {"measure": name, "n": n, "of": t, "rule": rule, "supports": claim, **extra}


def measures(atlas: Atlas) -> dict[str, Any]:
    queue.seed(atlas)
    con, sid = open_for(atlas), atlas.sid
    objs = [u for u, (t, _) in atlas.objects.items() if t not in queue.CONTAINERS]
    failed = census.parse_failures(atlas)
    clean = [u for u in objs if u not in failed and u not in atlas.outside]
    all_doors = doors.doors(atlas)
    status = {
        (k, s): st
        for k, s, st in con.execute(
            "SELECT kind, subject, status FROM items WHERE snapshot_id = ?", (sid,)
        )
    }
    assessed = [d for d in all_doors if status.get(("assess_entry", d["id"])) == "done"]
    partial = [d for d in all_doors if status.get(("assess_entry", d["id"])) == "done-partial"]
    blocked = [
        d for d in all_doors if status.get(("assess_entry", d["id"])) in {"blocked", "needs-human"}
    ]
    read = {
        o for (o,) in con.execute("SELECT DISTINCT object FROM reads WHERE snapshot_id = ?", (sid,))
    }
    described = [u for u in objs if status.get(("describe_object", u)) in {"done", "done-partial"}]
    marks = labels.labels(atlas)
    terminal = {"core", "shared", "supporting", "excluded"}
    accounted = [
        u for u in objs if marks[u][0] in terminal and (marks[u][0] != "core" or u in described)
    ]
    ds = drafts.build(atlas)
    approved = [d for d in ds if d["status"] == "approved"]
    ucs = usecases.build(atlas)
    with_uc = {u["feature"] for u in ucs if u["status"] == "approved"}
    selected = {
        t for (t,) in con.execute("SELECT target FROM decisions WHERE kind = 'select_runtime'")
    }
    observed = {
        c
        for (c,) in atlas.con.execute(
            "SELECT DISTINCT claim FROM findings WHERE snapshot_id = ? AND claim IS NOT NULL",
            (sid,),
        )
    }
    return {
        "snapshot": sid,
        "measures": [
            _m(
                "import",
                len(clean),
                len(objs),
                "objects whose logic was read and whose references all resolve",
                "the map holds N of T objects without known gaps; not that it holds the app",
                gaps={"logic not read": len(failed), "points outside": len(atlas.outside)},
            ),
            _m(
                "doors listed",
                len(all_doors),
                len(all_doors),
                "every door found, with its trigger and gates (or none)",
                "every door the export shows is listed",
                no_actor_evidence=sum(
                    1 for d in all_doors if not d["gates"] and not d["permission"].get("found")
                ),
            ),
            _m(
                "doors assessed",
                len(assessed),
                len(all_doors),
                "assessment done with no read left cut short; partial and blocked are not counted",
                "N doors traced to what they start, write and show",
                partial=len(partial),
                blocked=len(blocked),
            ),
            _m(
                "objects read",
                len(read & set(objs)),
                len(objs),
                "objects any step opened",
                "opened, not understood",
            ),
            _m(
                "objects described",
                len(described),
                len(objs),
                "objects with a verified note",
                "N objects have a checked description",
            ),
            _m(
                "objects accounted for",
                len(accounted),
                len(objs),
                "core (and described), shared, supporting or excluded; each object once",
                "N objects are accounted for, not understood",
                not_yet={
                    lab: sum(1 for u in objs if marks[u][0] == lab and u not in accounted)
                    for lab in ("core", "unreached")
                },
            ),
            _m(
                "feature drafts",
                len(ds),
                None,
                "a count: nobody knows how many features exist",
                "N drafts proposed so far",
                sizes=sorted((len(d["doors"]) for d in ds), reverse=True)[:10],
            ),
            _m(
                "features approved",
                len(approved),
                len(ds),
                "approved on their current inputs; stale approvals are not counted",
                "N of the drafts now proposed have an approved boundary",
                stale=sum(1 for d in ds if d["status"] == "stale"),
            ),
            _m(
                "use cases",
                len(with_uc),
                len(approved),
                "approved features with an approved use case",
                "N approved features have reviewed use cases",
                drafted=len(ucs),
            ),
            _m(
                "test design",
                None,
                None,
                "per technique: coverage items with an approved test idea",
                "per technique only",
                by_technique={
                    k: {"n": a, "of": b}
                    for k, a, b in ((k, *v) for k, v in testideas.coverage_items(atlas).items())
                },
            ),
            _m(
                "runtime checks",
                len(observed & selected),
                len(selected),
                "claims picked for a runtime "
                "check that have a runtime finding; never changes the measures above",
                "N picked claims were seen in an authorised environment",
            ),
        ],
        "health": health(atlas),
    }


def health(atlas: Atlas) -> dict[str, Any]:
    con, sid = open_for(atlas), atlas.sid
    statuses = dict(
        con.execute(
            "SELECT status, COUNT(*) FROM items WHERE snapshot_id = ? GROUP BY status", (sid,)
        ).fetchall()
    )
    cut = con.execute(
        "SELECT COUNT(*) FROM reads WHERE snapshot_id = ? AND truncated = 1 AND resolved = 0",
        (sid,),
    ).fetchone()[0]
    c = census.census(atlas)
    return {
        "items": statuses,
        "reads_cut_short": cut,
        "logic_not_read": c["logic_sources"]["not_read"],
        "failed_checks": c["failed_checks"],
        "processes_over_path_limit": c["processes_over_path_limit"],
        "open_questions": con.execute(
            "SELECT COUNT(*) FROM questions WHERE snapshot_id = ? AND status = 'open'", (sid,)
        ).fetchone()[0],
    }
