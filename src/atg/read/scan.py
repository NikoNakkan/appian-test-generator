"""Scan one parsed file: explicit references (SAIL, types) and every UUID token it contains.

Tokens that are not obviously self/version/explicit stay *pending*; link.py decides whether
they are internal ids or references once every object in the export is known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from atg.model import Reference, RefKind, UuidToken, UuidUse
from atg.read.known import PLATFORM_TYPE_NAMESPACES, VERSION_TAGS
from atg.read.xmlutil import UUID_RE, child_text, local

CANONICAL_RE = re.compile(r'#"([^"\n]{1,400})"')
TYPE_BANG_RE = re.compile(r"type!\{([^}]+)\}(\w+)")
# #"urn:appian:function:v1:a:currency" is a built-in function, like SYSTEM_SYSRULES_*.
_PLATFORM_PREFIXES = ("SYSTEM_", "urn:appian:function:")
# Urns whose first UUID is a record type: record-type, record-field, user-filter (rt/filter)...
_RECORD_URNS = ("urn:appian:record-", "urn:appian:user-filter:")
# Tags that define an id inside the file (besides <uuid>), e.g. a timer trigger's persistentId.
_DEFINING_TAGS = frozenset({"uuid", "persistentId"})


@dataclass(frozen=True)
class Pending:
    token: str
    defining: bool  # found in a <uuid> tag or uuid attribute: may define an internal id
    context: str


@dataclass
class FileScan:
    references: list[Reference] = field(default_factory=list)
    tokens: list[UuidToken] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)


def scan(root: Element, self_uuid: str) -> FileScan:
    out = FileScan()
    for elem in root.iter():
        tag = local(elem.tag)
        for key, value in elem.attrib.items():
            name = local(key)
            _scan_value(
                out,
                self_uuid,
                value,
                f"@{name}",
                version=name == "versionUuid",
                defining=name == "uuid",
            )
        if elem.text and elem.text.strip():
            _scan_value(
                out,
                self_uuid,
                elem.text,
                tag,
                version=tag in VERSION_TAGS,
                defining=tag in _DEFINING_TAGS,
            )
        if tag == "type":
            _structural_type(out, self_uuid, elem)
    return out


def _scan_value(
    out: FileScan, self_uuid: str, text: str, context: str, *, version: bool, defining: bool
) -> None:
    handled = _canonical_refs(out, self_uuid, text) if '#"' in text else set()
    for m in TYPE_BANG_RE.finditer(text):
        ns, name = m.group(1), m.group(2)
        if ns not in PLATFORM_TYPE_NAMESPACES:
            out.references.append(Reference(self_uuid, RefKind.TYPE, f"{{{ns}}}{name}", context))
    for m in UUID_RE.finditer(text):
        if m.start() in handled:
            continue
        token = m.group(0)
        if version:
            out.tokens.append(UuidToken(token, UuidUse.VERSION))
        elif token == self_uuid:
            out.tokens.append(UuidToken(token, UuidUse.SELF))
        else:
            out.pending.append(Pending(token, defining, context))


def _canonical_refs(out: FileScan, self_uuid: str, text: str) -> set[int]:
    """Record #"..." references; return start offsets of the UUID tokens they consumed."""
    handled: set[int] = set()
    for m in CANONICAL_RE.finditer(text):
        inner, base = m.group(1), m.start(1)
        uuids = list(UUID_RE.finditer(inner))
        if inner.startswith(_PLATFORM_PREFIXES):
            out.references.append(Reference(self_uuid, RefKind.PLATFORM, inner, "sail"))
        elif inner.startswith(_RECORD_URNS) and uuids:
            rt = uuids[0].group(0)
            is_self = rt == self_uuid  # a record type using its own fields
            kind = RefKind.SELF if is_self else RefKind.RECORD_TYPE
            out.references.append(Reference(self_uuid, kind, rt, inner))
            out.tokens.append(UuidToken(rt, UuidUse.SELF if is_self else UuidUse.REFERENCE))
            out.tokens.extend(UuidToken(u.group(0), UuidUse.URN_PART) for u in uuids[1:])
        elif len(uuids) == 1 and uuids[0].group(0) == inner:
            is_self = inner == self_uuid  # recursion
            kind = RefKind.SELF if is_self else RefKind.SAIL
            out.references.append(Reference(self_uuid, kind, inner, "sail"))
            out.tokens.append(UuidToken(inner, UuidUse.SELF if is_self else UuidUse.REFERENCE))
        else:
            out.references.append(Reference(self_uuid, RefKind.SAIL_NAME, inner, "sail"))
            continue  # any UUIDs inside a by-name ref stay pending
        handled.update(base + u.start() for u in uuids)
    return handled


def _structural_type(out: FileScan, self_uuid: str, elem: Element) -> None:
    """<type><name>X</name><namespace>NS</namespace></type> -> a reference to datatype {NS}X."""
    name = child_text(elem, "name").removesuffix("?list")
    ns = child_text(elem, "namespace")
    if name and ns and ns not in PLATFORM_TYPE_NAMESPACES and not UUID_RE.fullmatch(name):
        out.references.append(Reference(self_uuid, RefKind.TYPE, f"{{{ns}}}{name}", "type"))
