"""Which running environments a person has allowed for runtime checks, and how.

mode: observe (look only: open pages, read what is shown) or act (may submit forms, which writes
data and calls integrations). A runtime finding that names an environment without a current
authorisation is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from atg.agent.atlas import Atlas
from atg.analysis.store import now, open_for

MODES = ("observe", "act")


def grant(
    atlas: Atlas, environment: str, scope: str, mode: str, by: str, days: int = 7
) -> dict[str, Any]:
    if mode not in MODES or not environment.strip() or not by.strip():
        return {"error": f"need environment, by, and mode one of {', '.join(MODES)}"}
    until = (datetime.now(UTC) + timedelta(days=days)).isoformat(timespec="seconds")
    con = open_for(atlas)
    with con:
        con.execute(
            "INSERT INTO authorisations (environment, scope, mode, by, granted_at, expires_at) "
            "VALUES (?,?,?,?,?,?)",
            (environment, scope or "all", mode, by, now(), until),
        )
    return {
        "granted": {
            "environment": environment,
            "scope": scope or "all",
            "mode": mode,
            "until": until,
        }
    }


def current(atlas: Atlas, environment: str) -> dict[str, Any] | None:
    row = (
        open_for(atlas)
        .execute(
            "SELECT scope, mode, by, expires_at FROM authorisations WHERE environment = ? "
            "AND expires_at > ? ORDER BY id DESC LIMIT 1",
            (environment, now()),
        )
        .fetchone()
    )
    return dict(zip(("scope", "mode", "by", "until"), row, strict=True)) if row else None
