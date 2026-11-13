"""Where a test opens things, as paths under the Appian base URL (Appian 24+ defaults).

  site page          /suite/sites/<site urlStub>/page/<page urlStub>
  record list        /suite/tempo/records/type/<record type urlStub>/view/all
  record view        open a row from the record list, then the view tab (<view urlStub>)
  tasks              /suite/tempo/tasks  (or a site's task page)
Stubs come from the export: site and page urlStub, record type urlStub, detailViewCfg urlStub.
"""

from __future__ import annotations

import sqlite3

from atg import mapdb

TASKS = "/suite/tempo/tasks"


def _stub(settings: list[dict[str, str]], label: str = "urlStub") -> str:
    return next((s["value"] for s in settings if s["label"] == label), "")


def site_pages(con: sqlite3.Connection, sid: int) -> dict[str, str]:
    """Page target (interface, report, ...) -> its site page path."""
    sites = {u: _stub(s) for u, s in mapdb.settings_by_type(con, sid, "site").items()}
    return {
        target: f"/suite/sites/{sites[owner]}/page/{page}"
        for owner, target, page in con.execute(
            "SELECT owner_uuid, target, description FROM entry_points "
            "WHERE snapshot_id = ? AND kind = 'site page'",
            (sid,),
        )
        if sites.get(owner) and page
    }


def record_lists(con: sqlite3.Connection, sid: int) -> dict[str, str]:
    """Record type -> its record list path."""
    return {
        u: f"/suite/tempo/records/type/{stub}/view/all"
        for u, s in mapdb.settings_by_type(con, sid, "recordType").items()
        if (stub := _stub(s))
    }


def record_views(con: sqlite3.Connection, sid: int) -> dict[str, str]:
    """Record type -> the stub of its first view (summary), the tab a test opens."""
    return {
        u: stub
        for u, s in mapdb.settings_by_type(con, sid, "recordType").items()
        if (stub := _stub(s, "detailViewCfg > urlStub"))
    }
