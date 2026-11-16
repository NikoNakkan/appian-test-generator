"""Analysis view: progress measures, feature drafts and their cards, open questions, the
lifecycle and access checks, and people's decisions (POST)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from atg.agent import atlas, doors, lifecycle, security
from atg.analysis import decide, drafts, progress, queue, testideas, usecases
from atg.analysis.store import open_for


def _questions(at: atlas.Atlas) -> list[dict[str, Any]]:
    return [
        {"id": i, "about": s, "text": t, "status": st, "answer": a}
        for i, s, t, st, a in open_for(at).execute(
            "SELECT id, subject, text, status, answer FROM questions WHERE snapshot_id = ? "
            "ORDER BY status DESC, id",
            (at.sid,),
        )
    ]


def views(
    sid: int, query: dict[str, str], base_url: str = ""
) -> dict[str, Callable[[sqlite3.Connection], Any]]:
    def on(fn: Callable[[atlas.Atlas], Any]) -> Callable[[sqlite3.Connection], Any]:
        def run(con: sqlite3.Connection) -> Any:
            at = atlas.load(con, sid)
            at.memo["base_url"] = base_url
            return fn(at)

        return run

    return {
        "analysis": on(lambda at: {**progress.measures(at), "items": queue.resume(at)["items"]}),
        "analysis-drafts": on(lambda at: drafts.build(at)),
        "analysis-draft": on(lambda at: drafts.card(at, query.get("key", ""))),
        "analysis-questions": on(_questions),
        "analysis-lifecycle": on(lambda at: lifecycle.lifecycle(at)),
        "analysis-access": on(lambda at: security.check(doors.doors(at))),
        "analysis-use-cases": on(lambda at: usecases.build(at)),
        "analysis-tests": on(lambda at: testideas.build(at)),
    }


def decision(con: sqlite3.Connection, sid: int, body: dict[str, Any]) -> dict[str, Any]:
    payload = body.get("payload") or {}
    return decide.decide(
        atlas.load(con, sid),
        str(body.get("kind", "")),
        str(body.get("target", "")),
        str(body.get("by", "")),
        str(body.get("reason", "")),
        payload if isinstance(payload, dict) else {},
        preview=bool(body.get("preview")),
    )
