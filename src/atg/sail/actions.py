"""What a person can do on a screen: buttons, record action items and process links.

Interfaces store functions under internal names (#"SYSTEM_SYSRULES_ButtonWidgetSubmit",
writeRecords_v2, startProcess3), so names are compared without case, a!, or version suffix.
For each action: its label, whether it submits the form, and what its saveInto does: processes
it starts, record types it writes or deletes, record actions it opens, and a!save calls.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from functools import lru_cache

from atg.read.xmlutil import UUID_RE
from atg.sail.ast import (
    Call,
    Canon,
    Name,
    Node,
    SailSyntaxError,
    Str,
    parse,
)
from atg.sail.printer import print_node
from atg.sail.walk import keyword, nodes, plain_name

_BUTTONS = {"buttonwidget", "buttonwidgetsubmit"}
_LINKS = {"startprocesslink", "recordactionitem", "dynamiclink"}
_START = {"startprocess", "startprocesslink"}
_WRITE = {"writerecords", "writetodatastoreentity", "writetomultipledatastoreentities"}
_DELETE = {"deleterecords", "deletefromdatastoreentities"}
_RECORD_URN = re.compile(r"urn:appian:record-(?:type|field|relationship):v\d+:([0-9a-f-]{36})")
_RI = re.compile(r"\bri!(\w+)")
_ACTION_URN = re.compile(r"urn:appian:record-action:v\d+:([0-9a-f-]{36})/([0-9a-f-]{36})")


@dataclass
class Action:
    kind: str  # button, record action, process link, link
    label: str
    submits: bool = False
    starts: list[str] = field(default_factory=list)  # process model UUIDs
    writes: list[str] = field(default_factory=list)  # record type UUIDs
    deletes: list[str] = field(default_factory=list)
    record_actions: list[str] = field(default_factory=list)  # "<record type>/<action uuid>"
    saves: int = 0
    sets: list[str] = field(default_factory=list)  # rule inputs its saveInto sets (ri!x)


def find(source: str) -> list[Action]:
    """Parsing is the slow part and screens are asked about again and again: the same text is
    parsed once per process; callers get their own copies."""
    return copy.deepcopy(list(_find(source)))


@lru_cache(maxsize=2048)
def _find(source: str) -> tuple[Action, ...]:
    try:
        root = parse(source).root
    except SailSyntaxError:
        return ()
    return tuple(a for n in nodes(root) if isinstance(n, Call) and (a := _action(n)))


def _action(call: Call) -> Action | None:
    name = plain_name(call.fn)
    if name not in _BUTTONS | _LINKS:
        return None
    kind = {"recordactionitem": "record action", "startprocesslink": "process link"}.get(
        name, "button" if name in _BUTTONS else "link"
    )
    label = keyword(call, "label")
    act = Action(kind, label.text.strip('"') if isinstance(label, Str) else "")
    submit = keyword(call, "submit")
    act.submits = name == "buttonwidgetsubmit" or (
        isinstance(submit, Name | Call) and _is_true(submit)
    )
    for n in nodes(call):
        if isinstance(n, Call):
            inner = plain_name(n.fn)
            text = _canon_text(n)
            if inner in _START:
                act.starts += [u for u in UUID_RE.findall(_canon_text(keyword(n, "processModel")))]
            elif inner in _WRITE:
                act.writes += _RECORD_URN.findall(text)
            elif inner in _DELETE:
                act.deletes += _RECORD_URN.findall(text)
            elif inner == "save":
                act.saves += 1
        if isinstance(n, Canon) and (m := _ACTION_URN.search(n.text)):
            act.record_actions.append(f"{m.group(1)}/{m.group(2)}")
    save_into = keyword(call, "saveInto")
    act.sets = sorted(set(_RI.findall(print_node(save_into)))) if save_into else []
    if name == "startprocesslink":
        act.starts += UUID_RE.findall(_canon_text(keyword(call, "processModel")))
    act.starts, act.writes = sorted(set(act.starts)), sorted(set(act.writes))
    act.deletes, act.record_actions = sorted(set(act.deletes)), sorted(set(act.record_actions))
    does = act.starts or act.writes or act.deletes or act.record_actions
    return act if kind != "link" or does else None  # plain links only navigate


def _is_true(n: Node) -> bool:
    if isinstance(n, Name):
        return n.text == "true"
    return isinstance(n, Call) and plain_name(n.fn) == "true"


def _canon_text(n: Node | None) -> str:
    return " ".join(x.text for x in nodes(n) if isinstance(x, Canon)) if n else ""
