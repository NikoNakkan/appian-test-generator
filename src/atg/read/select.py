"""Pick the reader for an export. Only 20+ is supported; older exports are refused, not guessed."""

from __future__ import annotations

from atg.read import haul
from atg.read.source import ExportRoot


class UnsupportedVersionError(Exception):
    pass


def reader_for(root: ExportRoot) -> str:
    if root.major >= haul.MIN_MAJOR:
        return haul.NAME
    raise UnsupportedVersionError(
        f"Appian {root.appian_version} at {root.path}: only {haul.MIN_MAJOR}+ is supported"
    )
