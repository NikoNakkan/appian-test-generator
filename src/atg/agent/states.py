"""Record states a door or condition depends on: comparisons of a status-like field or variable
with a text value (status = "Approved", estado <> "Cerrado"). Read from SAIL as written."""

from __future__ import annotations

import re

from atg.agent.atlas import Atlas
from atg.textfold import fold

_CMP = re.compile(
    r'(?:#"urn:appian:record-field:v\d+:[0-9a-f-]{36}/([0-9a-f-]{36})"\]?'
    r"|\b(?:pv|ri|local|rv|fv|ac)!(?:[\w.]+\.)?(\w+))\s*(=|<>)\s*\"([^\"]*)\""
)
# English, Spanish and Greek (compared without case or accents).
_STATUSISH = (
    "status",
    "state",
    "estado",
    "stage",
    "phase",
    "step",
    "decision",
    "κατασταση",
    "σταδιο",
    "φαση",
    "βημα",
    "αποφαση",
)


def statusish(name: str) -> bool:
    low = fold(name)
    return any(w in low for w in _STATUSISH)


def predicates(atlas: Atlas, text: str) -> list[str]:
    out = []
    for field_uuid, var, op, value in _CMP.findall(text):
        name = atlas.names.fields.get(field_uuid, "") if field_uuid else var
        if name and statusish(name):
            out.append(f'{name} {"is" if op == "=" else "is not"} "{value}"')
    return list(dict.fromkeys(out))
