"""Reader for Appian 20+ exports ("Haul" XML, one object per file, XSD datatypes).

Real exports from 20.1 to 26.6 share this format; versions differ only in which object and
node types appear, which known.py lists.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from atg.model import AppObject, Reference, RefKind, Unknown, UnknownKind
from atg.read import details, entry, process, records
from atg.read.hashing import content_hash
from atg.read.known import (
    CONTENT_SUBTYPES,
    HAUL_METADATA,
    HAUL_ROOTS,
    NODE_TYPES,
    PLATFORM_TYPE_NAMESPACES,
)
from atg.read.scan import FileScan, scan
from atg.read.xmlutil import attr, child, child_text, local

NAME = "haul"
MIN_MAJOR = 20

_XMLNS_RE = re.compile(r'xmlns:(\w+)="([^"]+)"')


def read_file(path: Path, rel: str) -> tuple[AppObject | None, list[Unknown], FileScan | None]:
    """Parse one export file. Returns the object, any unknowns, and its scan for linking."""
    text = path.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return None, [Unknown(UnknownKind.PARSE_ERROR, str(e), rel)], None
    if path.suffix.lower() == ".xsd":
        return _read_xsd(root, text, rel)
    root_tag = local(root.tag)
    if root_tag not in HAUL_ROOTS:
        return None, [Unknown(UnknownKind.HAUL_ROOT, root_tag, rel)], None
    obj, unknowns = _identify(root, root_tag, rel)
    if obj is None:
        return None, unknowns, None
    obj.content_hash = content_hash(root)
    if root_tag == "processModelHaul":
        pm = process.find_pm(root)
        if pm is not None:
            obj.nodes, obj.flows = process.extract(pm)
            obj.node_details = process.node_details(pm)
            unknowns += [
                Unknown(UnknownKind.NODE_TYPE, n.type_id, rel)
                for n in obj.nodes
                if n.type_id not in NODE_TYPES
            ]
    elif root_tag == "siteHaul":
        obj.entry_points = entry.site_pages(root)
    elif root_tag == "recordTypeHaul":
        obj.entry_points = entry.record_actions(root)
    return obj, unknowns, scan(root, obj.uuid)


def _identify(root: Element, root_tag: str, rel: str) -> tuple[AppObject | None, list[Unknown]]:
    inner = next((c for c in root if local(c.tag) not in HAUL_METADATA), None)
    if inner is None:
        return None, [Unknown(UnknownKind.NO_UUID, root_tag, rel)]
    obj_type = HAUL_ROOTS[root_tag]
    if root_tag == "contentHaul":
        sub = local(inner.tag)
        if sub not in CONTENT_SUBTYPES:
            return None, [Unknown(UnknownKind.CONTENT_SUBTYPE, sub, rel)]
        obj_type = CONTENT_SUBTYPES[sub]
    if root_tag == "processModelHaul":
        pm = process.find_pm(root)
        uuid, name = process.pm_identity(pm) if pm is not None else ("", "")
    else:
        uuid = child_text(inner, "uuid") or attr(inner, "uuid")
        name = child_text(inner, "name") or attr(inner, "name")
    if not uuid:
        return None, [Unknown(UnknownKind.NO_UUID, root_tag, rel)]
    obj = AppObject(uuid=uuid, type=obj_type, name=name, path=rel, haul_root=root_tag)
    pm = process.find_pm(root) if root_tag == "processModelHaul" else None
    obj.details = details.object_details(inner, obj_type, pm)
    if obj_type in {"rule", "interface"} and (tests := records.saved_tests(root)):
        obj.details["saved_tests"] = tests
    definition = child(inner, "definition")
    if definition is not None and definition.text and definition.text.strip():
        obj.definition = definition.text  # SAIL source, parsed by Layer 2
    return obj, []


def _read_xsd(
    root: Element, text: str, rel: str
) -> tuple[AppObject | None, list[Unknown], FileScan | None]:
    """A datatype: identity is {targetNamespace}Name, the same key SAIL uses in type!{ns}Name."""
    ns = root.get("targetNamespace", "")
    ctype = child(root, "complexType")
    if ctype is None or not ns:
        return None, [Unknown(UnknownKind.NO_UUID, "xsd", rel)], None
    name = ctype.get("name", "")
    key = f"{{{ns}}}{name}"
    obj = AppObject(uuid=key, type="datatype", name=name, path=rel, haul_root="xsd")
    obj.details = {"description": "", "fields": details.xsd_fields(root)}
    obj.content_hash = content_hash(root)
    file_scan = scan(root, key)
    prefixes = dict(_XMLNS_RE.findall(text))
    for elem in root.iter():
        type_attr = elem.get("type", "")
        prefix, _, local_name = type_attr.rpartition(":")
        target_ns = prefixes.get(prefix, "")
        if local_name and target_ns and target_ns not in PLATFORM_TYPE_NAMESPACES:
            target = f"{{{target_ns}}}{local_name}"
            file_scan.references.append(Reference(key, RefKind.TYPE, target, "xsd"))
    return obj, [], file_scan


# Notes people keep next to an export in a repository; not part of the export itself.
REPO_NOTES = frozenset({".md", ".gitignore", ".gitattributes", ".gitkeep"})


def is_repo_note(rel_parts: tuple[str, ...]) -> bool:
    return Path(rel_parts[-1]).suffix.lower() in REPO_NOTES or rel_parts[-1] in REPO_NOTES


def is_binary_document(rel_parts: tuple[str, ...]) -> bool:
    """Document content lives at content/<documentUuid>/<file>."""
    return len(rel_parts) == 3 and rel_parts[0] == "content"
