"""Object security as exported: the role map that says which groups hold which role.

Appian keeps each object's security next to it in the haul as a roleMap with role elements
(for example processModelInitiator, processModelViewer, viewer, editor, administrator), each
listing groups and users. Users are never exported between environments, so only the groups
are useful; allowForAll="true" (or an "all users"/public flag) means everyone holds the role.
The exact tag layout is not published, so this reads it loosely: any element named role under
any element named roleMap, the role's name from its name attribute or child, and group
identifiers from elements whose tag mentions "group".
"""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

from atg.read.xmlutil import child_text, local


def role_map(root: Element) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rm in (e for e in root.iter() if local(e.tag) == "roleMap"):
        public = rm.get("public", "").lower() == "true"
        for role in (e for e in rm.iter() if local(e.tag) == "role"):
            name = role.get("name") or child_text(role, "name")
            groups = [
                (g.text or "").strip()
                for g in role.iter()
                if "group" in local(g.tag).lower() and len(g) == 0 and (g.text or "").strip()
            ]
            users = sum(
                1
                for u in role.iter()
                if "user" in local(u.tag).lower() and len(u) == 0 and (u.text or "").strip()
            )
            everyone = public or role.get("allowForAll", "").lower() == "true"
            if name:
                out.append({"role": name, "groups": groups, "users": users, "everyone": everyone})
    return out
