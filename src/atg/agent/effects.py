"""What a process node changes, in words: records written or deleted, statuses set, tasks given
to people, processes started (directly, through a constant or an expression), integrations,
emails. Script tasks that only set process variables change nothing outside the process.
"""

from __future__ import annotations

import json
import re

from atg import mapdb
from atg.agent.atlas import Atlas

SET_FIELD = re.compile(
    r'#"urn:appian:record-field:v\d+:[0-9a-f-]{36}/([0-9a-f-]{36})"\s*,\s*"([^"]*)"'
)
_TOKEN = re.compile(
    r'#"([^"]+)"|\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b'
)
_KINDS = (
    ("delete", "deletes data"),
    ("write", "writes records"),
    ("email", "sends an email"),
    ("message", "sends a message"),
    ("document", "creates or changes a document"),
)
TASK = "internal.17"
SUBPROCESS = "internal.38"


def assignee(a: str, atlas: Atlas) -> str:
    if "pp!initiator" in a:
        return "the person who started it"
    return mapdb.assignee_name(a, atlas.objects)


def _tokens(text: str) -> list[str]:
    return [a or b for a, b in _TOKEN.findall(text)]


def node_effects(atlas: Atlas, pm: str) -> dict[int, list[str]]:
    """guiId -> what that node changes (only nodes that change something are listed)."""
    inputs = {
        g: json.loads(d or "{}").get("inputs", [])
        for g, d in atlas.con.execute(
            "SELECT gui_id, details FROM node_details WHERE snapshot_id = ? AND pm_uuid = ?",
            (atlas.sid, pm),
        )
    }
    out: dict[int, list[str]] = {}
    for gui, type_id, type_name, calls, assignees in atlas.con.execute(
        "SELECT gui_id, type_id, type_name, calls, assignees FROM nodes "
        "WHERE snapshot_id = ? AND pm_uuid = ?",
        (atlas.sid, pm),
    ):
        said: list[str] = []
        kind = f"{type_id} {type_name}".lower()
        if type_id == TASK:
            who = [assignee(a, atlas) for a in json.loads(assignees or "[]")]
            said.append("gives a task to " + (", ".join(who) or "someone not set in the export"))
        said += [text for key, text in _KINDS if key in kind and "integration" not in kind]
        code = " ".join(str(i.get("expr") or i.get("value") or "") for i in inputs.get(gui, []))
        said += _statuses(atlas, code)
        started = [calls] if calls else []
        started += [u for t in _tokens(code) for u in atlas.resolve(t)]
        for u in dict.fromkeys(started):
            if atlas.type(u) == "processModel" and u != pm:
                said.append(f"starts process {atlas.name(u)}")
            elif atlas.type(u) == "integration":
                said.append(f"calls integration {atlas.name(u)}")
        if type_id == SUBPROCESS and not any(s.startswith("starts") for s in said):
            said.append("starts a process chosen at run time or outside this export")
        if said:
            out[gui] = list(dict.fromkeys(said))
    return out


def _statuses(atlas: Atlas, code: str) -> list[str]:
    return [
        f'sets {atlas.names.fields.get(f, "a field")} to "{v}"' for f, v in SET_FIELD.findall(code)
    ]
