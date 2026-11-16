"""What the map holds and what it cannot see, counted by plain queries (no interpretation).

UNKNOWNS lists what an export never contains, so a claim about access or behaviour can cite
the reason it cannot be settled from the export alone.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from atg.agent.atlas import Atlas

UNKNOWNS = {
    "members": "who is in each group (exports keep groups, never their members)",
    "users": "user accounts and their profile values",
    "data": "record data, so ownership and status of real records",
    "instances": "running or finished process instances and their history",
    "environment": "environment-specific values (URLs, credentials, import customisation)",
    "plugins": "plug-in code and smart services not in the package",
    "admin": "Admin Console settings that change behaviour",
}


def census(atlas: Atlas) -> dict[str, Any]:
    con, sid = atlas.con, atlas.sid
    parse = dict(
        con.execute(
            "SELECT ok, COUNT(*) FROM sail_parse WHERE snapshot_id = ? GROUP BY ok", (sid,)
        ).fetchall()
    )
    outside = con.execute(
        "SELECT kind, COUNT(DISTINCT target), SUM(occurrences) FROM refs "
        "WHERE snapshot_id = ? AND resolved = 0 GROUP BY kind ORDER BY 2 DESC",
        (sid,),
    ).fetchall()
    unknown = con.execute(
        "SELECT kind, value, COUNT(*) FROM unknowns WHERE snapshot_id = ? GROUP BY kind, value",
        (sid,),
    ).fetchall()
    failed = con.execute(
        "SELECT layer, name FROM check_results WHERE snapshot_id = ? AND ok = 0", (sid,)
    ).fetchall()
    truncated = con.execute(
        "SELECT COUNT(*) FROM path_stats WHERE snapshot_id = ? AND truncated = 1", (sid,)
    ).fetchone()[0]
    return {
        "objects": dict(Counter(t for t, _ in atlas.objects.values()).most_common()),
        "logic_sources": {"read": parse.get(1, 0), "not_read": parse.get(0, 0)},
        "references_outside_export": [{"kind": k, "targets": t, "uses": n} for k, t, n in outside],
        "not_supported": [{"kind": k, "value": v, "files": n} for k, v, n in unknown],
        "failed_checks": [f"layer {layer}: {name}" for layer, name in failed],
        "processes_over_path_limit": truncated,
        "never_in_an_export": UNKNOWNS,
    }


def parse_failures(atlas: Atlas) -> set[str]:
    return {
        u
        for (u,) in atlas.con.execute(
            "SELECT DISTINCT owner_uuid FROM sail_parse WHERE snapshot_id = ? AND ok = 0",
            (atlas.sid,),
        )
    }
