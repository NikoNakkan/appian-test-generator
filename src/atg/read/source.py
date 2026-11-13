"""Find export roots and their files. An export root is a folder holding META-INF/MANIFEST.MF."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

_VERSION_RE = re.compile(r"^Appian-Version:\s*(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class ExportRoot:
    path: Path
    appian_version: str

    @property
    def major(self) -> int:
        head = self.appian_version.split(".", 1)[0]
        return int(head) if head.isdigit() else 0


def find_roots(path: Path) -> list[ExportRoot]:
    """All export roots at or below `path`. Zips are extracted next to themselves first."""
    if path.is_file() and path.suffix.lower() == ".zip":
        path = _extract(path)
    roots: dict[Path, ExportRoot] = {}
    for manifest in sorted(path.rglob("MANIFEST.MF")):
        if ".git" in manifest.parts or "META-INF" not in manifest.parts:
            continue
        # Usually META-INF/MANIFEST.MF; patch and multi-app exports nest it one level deeper,
        # META-INF/<app id>/MANIFEST.MF. The export root is the folder holding META-INF.
        meta = next(p for p in manifest.parents if p.name == "META-INF")
        roots.setdefault(meta.parent, ExportRoot(meta.parent, read_version(manifest)))
    return list(roots.values())


def read_version(manifest: Path) -> str:
    match = _VERSION_RE.search(manifest.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else "unknown"


def export_files(root: Path) -> list[Path]:
    """Every file in the export except META-INF and VCS folders, sorted for stable output."""
    skip = {"META-INF", ".git"}
    return sorted(
        p for p in root.rglob("*") if p.is_file() and not skip & set(p.relative_to(root).parts)
    )


MAX_ZIP_FILES = 100_000
MAX_ZIP_BYTES = 4 * 1024**3  # 4 GB unpacked


class UnsafeZipError(ValueError):
    pass


def _extract(zip_path: Path) -> Path:
    """Unpack next to the zip, refusing anything that could escape the folder or fill the disk:
    absolute paths, "..", too many files, or too many bytes once unpacked."""
    target = zip_path.with_suffix("")
    if target.exists():
        return target
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if len(members) > MAX_ZIP_FILES or sum(m.file_size for m in members) > MAX_ZIP_BYTES:
            raise UnsafeZipError(f"{zip_path.name} is too large to unpack safely.")
        root = target.resolve()
        for m in members:
            dest = (target / m.filename).resolve()
            if m.filename.startswith(("/", "\\")) or (dest != root and root not in dest.parents):
                raise UnsafeZipError(
                    f"{zip_path.name} has an entry outside its folder: {m.filename}"
                )
        zf.extractall(target)
    return target
