"""Work items: what the agent should look at next, chosen by code, never by the model.

Order: items a person's answer just unblocked; doors not yet assessed (those reaching the most
objects nobody has read first, then doors that start or write something, then trigger types
seen least so far); objects used by an assessed door and not yet described; record-type
lifecycles; gaps; the reconcile pass; challenges of feature drafts; everything else. Ties go
by id, so the order is the same on every run. Leases expire, so a crashed session loses
nothing: resume() puts expired leases back and lists what is open.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from atg.agent import census, doors, reach
from atg.agent.atlas import Atlas
from atg.analysis.store import PARAMS, content_hash, digest, idempotency_key, now, open_for

QUESTIONS = {
    "Q1": "What does this door start or write?",
    "Q2": "Which record type and which status values are involved?",
    "Q3": "Who is given the tasks, and can they be reassigned?",
    "Q4": "What guards the door, and does it only hide it or actually refuse?",
    "Q5": "Which other doors start the same process or show the same screen?",
    "Q6": "What leaves the application (integration, email, document)?",
}
ORDER = ["assess_entry", "describe_object", "lifecycle", "classify_gap", "reconcile", "challenge"]
CONTAINERS = frozenset(
    {"application", "folder", "rulesFolder", "processModelFolder", "knowledgeCenter", "document"}
)
LEASE = timedelta(minutes=30)
WRITING = ("action", "start", "api")


def input_hash(atlas: Atlas, kind: str, subject: str) -> str:
    if kind == "assess_entry":
        d = doors.by_id(atlas, subject) or {}
        opens = (d.get("opens") or {}).get("id", "")
        return digest(
            content_hash(atlas, d.get("in_id", "")),
            content_hash(atlas, opens),
            d.get("gate_as_written", ""),
        )
    if kind == "reconcile":
        return digest(sorted(atlas.memo.get("hashes", {}).values()))
    return content_hash(atlas, subject.split(":")[-1])


def _rows(atlas: Atlas) -> list[tuple[str, str]]:
    rows = [("assess_entry", d["id"]) for d in doors.doors(atlas)]
    rows += [("describe_object", u) for u, (t, _) in atlas.objects.items() if t not in CONTAINERS]
    rows += [("lifecycle", u) for u, (t, _) in atlas.objects.items() if t == "recordType"]
    gaps = set(atlas.outside) | census.parse_failures(atlas)
    rows += [("classify_gap", u) for u in sorted(gaps)]
    return [*rows, ("reconcile", "all")]


def seed(atlas: Atlas) -> int:
    """Create this snapshot's items once; reuse finished work whose inputs did not change."""
    con = open_for(atlas)
    if con.execute("SELECT 1 FROM items WHERE snapshot_id = ? LIMIT 1", (atlas.sid,)).fetchone():
        return 0
    content_hash(atlas, "")  # load hashes
    with con:
        for kind, subject in _rows(atlas):
            add(atlas, con, kind, subject)
    return len(_rows(atlas))


def add(atlas: Atlas, con: sqlite3.Connection, kind: str, subject: str, h: str = "") -> None:
    key = idempotency_key(kind, subject, h or input_hash(atlas, kind, subject))
    item_id = f"{kind}:{subject}"
    old = con.execute(
        "SELECT snapshot_id, status FROM items WHERE key = ? AND snapshot_id <> ? "
        "AND status IN ('done', 'done-partial') ORDER BY snapshot_id DESC LIMIT 1",
        (key, atlas.sid),
    ).fetchone()
    status, note = ("pending", "") if not old else (old[1], f"reused from snapshot {old[0]}")
    con.execute(
        "INSERT OR IGNORE INTO items (snapshot_id, id, kind, subject, key, status, priority, "
        "note, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (atlas.sid, item_id, kind, subject, key, status, 5, note, now()),
    )
    if old:
        _copy(con, key, old[0], atlas.sid)


def _copy(con: sqlite3.Connection, key: str, src: int, dst: int) -> None:
    con.execute(
        "INSERT INTO claims (snapshot_id, item_id, key, subject, predicate, value, level, "
        "evidence, input_hash, model, at) SELECT ?, item_id, key, subject, predicate, value, "
        "level, evidence, input_hash, model, at FROM claims WHERE key = ? AND snapshot_id = ?",
        (dst, key, src),
    )


def resume(atlas: Atlas) -> dict[str, Any]:
    seed(atlas)
    con = open_for(atlas)
    with con:
        con.execute(
            "UPDATE items SET status = 'pending', lease_until = NULL WHERE snapshot_id = ? "
            "AND status = 'leased' AND lease_until < ?",
            (atlas.sid, now()),
        )
        con.execute(
            "UPDATE items SET status = 'pending', priority = 0 WHERE snapshot_id = ? AND "
            "status = 'needs-human' AND id IN (SELECT item_id FROM questions WHERE "
            "snapshot_id = ? AND status = 'answered')",
            (atlas.sid, atlas.sid),
        )
    counts = dict(
        con.execute(
            "SELECT status, COUNT(*) FROM items WHERE snapshot_id = ? GROUP BY status", (atlas.sid,)
        ).fetchall()
    )
    open_q = con.execute(
        "SELECT id, subject, text FROM questions WHERE snapshot_id = ? AND "
        "status = 'open' ORDER BY id",
        (atlas.sid,),
    ).fetchall()
    last = con.execute(
        "SELECT item_id, subject, predicate, value FROM claims WHERE "
        "snapshot_id = ? ORDER BY id DESC LIMIT 20",
        (atlas.sid,),
    ).fetchall()
    return {
        "snapshot": atlas.sid,
        "items": counts,
        "parameters": PARAMS,
        "open_questions": [{"id": i, "about": s, "text": t} for i, s, t in open_q],
        "last_claims": [
            {"item": i, "subject": s, "predicate": p, "value": v} for i, s, p, v in last
        ],
    }


def pick(atlas: Atlas) -> tuple[str, str, str] | None:
    con = open_for(atlas)
    pending = con.execute(
        "SELECT id, kind, subject, priority FROM items "
        "WHERE snapshot_id = ? AND status = 'pending'",
        (atlas.sid,),
    ).fetchall()
    if not pending:
        return None
    done = {
        s
        for (s,) in con.execute(
            "SELECT subject FROM items WHERE snapshot_id = ? AND "
            "kind = 'assess_entry' AND status IN ('done', 'done-partial')",
            (atlas.sid,),
        )
    }
    seen = {
        o
        for (o,) in con.execute(
            "SELECT DISTINCT object FROM reads WHERE snapshot_id = ?", (atlas.sid,)
        )
    }
    reached = reach.reach(atlas)
    by_trigger: dict[str, int] = {}
    for d in doors.doors(atlas):
        if d["id"] in done:
            by_trigger[d["trigger"]] = by_trigger.get(d["trigger"], 0) + 1
    cited = set().union(*(reached.get(s, set()) for s in done)) if done else set()
    trig = {d["id"]: d["trigger"] for d in doors.doors(atlas)}

    def score(row: tuple[str, str, str, int]) -> tuple[Any, ...]:
        item_id, kind, subject, prio = row
        if prio == 0:
            return (0, 0, 0, 0, item_id)
        if kind == "assess_entry":
            unseen = len(reached.get(subject, set()) - seen)
            writes = 0 if subject.startswith(WRITING) else 1
            return (1, -unseen, writes, by_trigger.get(trig.get(subject, ""), 0), item_id)
        if kind == "describe_object" and subject in cited:
            return (2, 0, 0, 0, item_id)
        return (3 + ORDER.index(kind) if kind in ORDER else 9, 0, 0, 0, item_id)

    best = min(pending, key=score)
    with con:
        until = (datetime.now(UTC) + LEASE).isoformat(timespec="seconds")
        con.execute(
            "UPDATE items SET status = 'leased', lease_until = ?, attempts = attempts + 1, "
            "updated_at = ? WHERE snapshot_id = ? AND id = ?",
            (until, now(), atlas.sid, best[0]),
        )
    return best[0], best[1], best[2]
