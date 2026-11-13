"""The Tests view: every test in one list (process paths, screens, rules) and each one's data."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from atg.testgen import scenarios, screens, testdata


def tests(con: sqlite3.Connection, sid: int) -> dict[str, Any]:
    objects = {
        u: (t, n)
        for u, t, n in con.execute(
            "SELECT uuid, type, name FROM objects WHERE snapshot_id = ?", (sid,)
        )
    }
    processes: dict[str, dict[str, Any]] = {}
    for pm, no, decisions, tasks in con.execute(
        "SELECT pm_uuid, path_no, decisions, tasks FROM paths WHERE snapshot_id = ? "
        "ORDER BY pm_uuid, path_no",
        (sid,),
    ):
        entry = processes.setdefault(
            pm, {"uuid": pm, "name": objects.get(pm, ("", pm))[1], "paths": []}
        )
        entry["paths"].append(
            {
                "no": no,
                "route": " → ".join(d["rule"] for d in json.loads(decisions)) or "straight through",
                "tasks": len(json.loads(tasks)),
            }
        )
    routes = screens.routes(con, sid)
    screen_list = [
        {
            "uuid": u,
            "name": objects[u][1],
            "how": sorted({r["how"] for r in rs}),
            "where": [r["where"] for r in rs][:3],
        }
        for u, rs in routes.items()
        if u in objects
    ]
    rules = []
    for u, (kind, name) in objects.items():
        if kind in {"rule", "decision"}:
            row = con.execute(
                "SELECT details FROM object_details WHERE snapshot_id = ? AND uuid = ?", (sid, u)
            ).fetchone()
            inputs = json.loads(row[0]).get("inputs", []) if row else []
            rules.append({"uuid": u, "name": name, "kind": kind, "inputs": len(inputs)})
    return {
        "processes": sorted(processes.values(), key=lambda p: p["name"]),
        "screens": sorted(screen_list, key=lambda s: s["name"]),
        "rules": sorted(rules, key=lambda r: r["name"]),
    }


def test_data(con: sqlite3.Connection, sid: int, uuid: str, path: int | None) -> dict[str, Any]:
    """The data one test needs: a process path, a screen, or a rule."""
    if path:
        return testdata.path_data(con, sid, uuid, path)
    row = con.execute(
        "SELECT type FROM objects WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
    ).fetchone()
    if row and row[0] == "interface":
        return {"kind": "screen", **screens.screen_data(con, sid, uuid)}
    return {"kind": "rule", **testdata.rule_data(con, sid, uuid)}


def scenario(con: sqlite3.Connection, sid: int, uuid: str, path: int | None) -> dict[str, Any]:
    """The UAT scenario for a process path or a screen (rules are unit tests, not UAT)."""
    if path:
        return scenarios.path_scenario(con, sid, uuid, path)
    row = con.execute(
        "SELECT type FROM objects WHERE snapshot_id = ? AND uuid = ?", (sid, uuid)
    ).fetchone()
    if row and row[0] == "interface":
        return scenarios.screen_scenario(con, sid, uuid)
    return {"error": "Rules are checked by unit tests, not UAT scenarios."}
