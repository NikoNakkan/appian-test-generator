"""Resolve pending UUID tokens once every object in the export is known.

A pending token is a REFERENCE if it names another object, INTERNAL if this file defines it
(e.g. a process node uuid, a record field uuid), otherwise a REFERENCE to something outside
the export — reported later as external.
"""

from __future__ import annotations

from atg.model import AppObject, Reference, RefKind, UuidToken, UuidUse
from atg.read.scan import FileScan


def link(scans: list[tuple[AppObject, FileScan]]) -> None:
    object_uuids = {obj.uuid for obj, _ in scans}
    for obj, file_scan in scans:
        defined = {p.token for p in file_scan.pending if p.defining} - object_uuids
        obj.internal_ids = defined
        obj.references = list(file_scan.references)
        obj.tokens = list(file_scan.tokens)
        for p in file_scan.pending:
            if p.token in object_uuids or p.token not in defined:
                obj.tokens.append(UuidToken(p.token, UuidUse.REFERENCE))
                obj.references.append(Reference(obj.uuid, RefKind.XML, p.token, p.context))
            else:
                obj.tokens.append(UuidToken(p.token, UuidUse.INTERNAL))


def resolvable_targets(objects: list[AppObject]) -> set[str]:
    """Everything a reference may legally point at: object uuids, datatype keys, internal ids."""
    targets = {o.uuid for o in objects}
    for o in objects:
        targets |= o.internal_ids
    return targets
