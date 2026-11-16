"""What starts each process: a person (through a page, record action, screen button or task),
a web API, a timer, a message, another process, or nothing found in this export.

Timer and message starts are recognised loosely from the start node's settings (names or
values mentioning timer, recurrence, schedule, message or signal), because the exported
layout of start-event triggers is not published.
"""

from __future__ import annotations

import json
import re
from typing import Any

from atg.agent.atlas import Atlas

_TIMER = re.compile(r"timer|recurr|schedul", re.IGNORECASE)
_MESSAGE = re.compile(r"message|signal", re.IGNORECASE)
_PEOPLE = {"recordType": "user", "site": "user", "interface": "user", "webApi": "api"}


def _start_settings(atlas: Atlas, pm: str) -> str:
    rows = atlas.con.execute(
        "SELECT n.type_name, n.label, d.details FROM nodes n LEFT JOIN node_details d "
        "ON d.snapshot_id = n.snapshot_id AND d.pm_uuid = n.pm_uuid AND d.gui_id = n.gui_id "
        "WHERE n.snapshot_id = ? AND n.pm_uuid = ? AND (n.type_id = 'core.0' "
        "OR n.type_name LIKE '%Start%')",
        (atlas.sid, pm),
    ).fetchall()
    return " ".join(f"{tn} {lab} {json.dumps(json.loads(d or '{}'))}" for tn, lab, d in rows)


def _callers(atlas: Atlas, pm: str) -> set[str]:
    kinds: set[str] = set()
    for u in atlas.used_by.get(pm, []):
        t = atlas.type(u)
        if t == "processModel":
            kinds.add("sub-process")
        elif t == "constant":  # a process named through a constant: who uses the constant?
            kinds |= {_PEOPLE.get(atlas.type(c), "sub-process") for c in atlas.used_by.get(u, [])}
        elif t in _PEOPLE:
            kinds.add(_PEOPLE[t])
    return kinds


def process_triggers(atlas: Atlas) -> dict[str, list[str]]:
    if "triggers" in atlas.memo:
        found: dict[str, list[str]] = atlas.memo["triggers"]
        return found
    out: dict[str, list[str]] = {}
    for pm, (t, _) in atlas.objects.items():
        if t != "processModel":
            continue
        settings = _start_settings(atlas, pm)
        kinds = _callers(atlas, pm)
        if _TIMER.search(settings):
            kinds.add("timer")
        if _MESSAGE.search(settings):
            kinds.add("message")
        out[pm] = sorted(kinds) or ["none found"]
    atlas.memo["triggers"] = out
    return out


def start_doors(atlas: Atlas) -> list[dict[str, Any]]:
    """Processes nobody starts from a screen: timers, messages, and ones with no start found."""
    out = []
    for pm, kinds in process_triggers(atlas).items():
        for kind in ("timer", "message", "none found"):
            if kind in kinds:
                out.append({"pm": pm, "trigger": kind})
    return out
