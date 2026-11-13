"""Read one export root into a Snapshot (no database involved)."""

from __future__ import annotations

from collections.abc import Callable

from atg.model import AppObject, Snapshot, Unknown, UnknownKind
from atg.read import haul
from atg.read.link import link
from atg.read.scan import FileScan
from atg.read.select import reader_for
from atg.read.source import ExportRoot, export_files

_DATA_SUFFIXES = {".xml", ".xsd"}

# (done, total) after each file; lets a UI show a progress bar.
FileProgress = Callable[[int, int], None]


def read_snapshot(root: ExportRoot, on_file: FileProgress | None = None) -> Snapshot:
    snap = Snapshot(
        source=str(root.path), appian_version=root.appian_version, reader=reader_for(root)
    )
    scans: list[tuple[AppObject, FileScan]] = []
    files = export_files(root.path)
    for done, path in enumerate(files, 1):
        if on_file is not None:
            on_file(done, len(files))
        rel_parts = path.relative_to(root.path).parts
        rel = "/".join(rel_parts)
        if path.suffix.lower() not in _DATA_SUFFIXES:
            if haul.is_binary_document(rel_parts):
                snap.binary_files.append(rel)
            elif haul.is_repo_note(rel_parts):
                pass  # a README or .gitignore kept next to the export
            else:
                snap.unknowns.append(Unknown(UnknownKind.FILE, path.suffix or path.name, rel))
            continue
        obj, unknowns, file_scan = haul.read_file(path, rel)
        snap.unknowns.extend(unknowns)
        if obj is not None and file_scan is not None:
            snap.objects.append(obj)
            scans.append((obj, file_scan))
    link(scans)
    return snap
