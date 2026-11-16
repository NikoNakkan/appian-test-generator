"""Who may see or do something, read from the SAIL that decides it.

Three kinds of gate: a group check (a!isUserMemberOfGroup, with the group named directly or
through a constant), the user's own data (loggedInUser() used to filter or compare), and the
user's profile (user(...) / a!userRecord...). Every gate says how sure we are: "read" when the
text names the group, "resolved" when a constant had to be followed, "unresolved" when the
group is not in this export.
"""

from __future__ import annotations

import re
from typing import Any

from atg.agent.atlas import Atlas

_GROUP_CALL = re.compile(r'isUserMemberOfGroup\w*"?\(', re.IGNORECASE)
_TOKEN = re.compile(r'#"([^"]+)"')
_OWN = re.compile(r'loggedInUser\w*"?\(\)', re.IGNORECASE)
_PROFILE = re.compile(r'(?:SYSTEM_SYSRULES_user|a!user)\w*"?\(', re.IGNORECASE)


def _args(text: str, start: int) -> str:
    """The text up to the bracket that closes the call opened just before start."""
    depth = 1
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i]
    return text[start:]


def group_checks(atlas: Atlas, text: str) -> list[dict[str, Any]]:
    out = []
    for m in _GROUP_CALL.finditer(text):
        found: list[str] = []
        via, unresolved = "read", 0
        for token in _TOKEN.findall(_args(text, m.end())):
            for u in atlas.resolve(token):
                if atlas.type(u) == "group":
                    found.append(atlas.name(u))
                    via = "resolved" if u != token else via
                elif atlas.type(token) == "constant" or token.startswith(("_e-", "_a-")):
                    unresolved += 1
        out.append({"groups": sorted(set(found)), "confidence": via, "unresolved": unresolved})
    return out


def gates_in(atlas: Atlas, text: str, where: str = "whole") -> list[dict[str, Any]]:
    """The gates a piece of SAIL contains. where: whole (the object) or part (of a screen)."""
    out: list[dict[str, Any]] = []
    for g in group_checks(atlas, text):
        names = g["groups"]
        say = "only members of " + (" or ".join(names) if names else "a group not in this export")
        conf = "unresolved" if g["unresolved"] and not names else g["confidence"]
        out.append({"kind": "group", "groups": names, "says": say, "confidence": conf})
    if _OWN.search(_without_group_checks(text)):
        out.append(
            {
                "kind": "own data",
                "groups": [],
                "says": "depends on who is logged in (their own records or user)",
                "confidence": "read",
            }
        )
    if _PROFILE.search(text):
        out.append(
            {
                "kind": "profile",
                "groups": [],
                "says": "depends on the user's profile fields",
                "confidence": "read",
            }
        )
    return [{**g, "where": where} for g in out]


def _without_group_checks(text: str) -> str:
    """The text minus the group checks: loggedInUser() there asks about a group, not own data."""
    for m in reversed(list(_GROUP_CALL.finditer(text))):
        text = text[: m.start()] + text[m.end() + len(_args(text, m.end())) :]
    return text


def group_ids(atlas: Atlas, text: str) -> set[str]:
    """UUIDs of every group a text checks (after following constants)."""
    return {
        u
        for m in _GROUP_CALL.finditer(text)
        for token in _TOKEN.findall(_args(text, m.end()))
        for u in atlas.resolve(token)
        if atlas.type(u) == "group"
    }
