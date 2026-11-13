"""Dumb text counts over the raw export. Deliberately shares nothing with the XML parser."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from atg.read.source import export_files
from atg.read.xmlutil import UUID_RE

_ROOT_RE = re.compile(r"<(\w+Haul)\b")


@dataclass
class RawCounts:
    data_files: int = 0
    roots: Counter[str] = field(default_factory=Counter)
    nodes: int = 0
    connections: int = 0
    gateway_rules: int = 0
    gateway_defaults: int = 0
    canonical_refs: int = 0
    uuids_by_path: dict[str, int] = field(default_factory=dict)


def count(root: Path) -> RawCounts:
    out = RawCounts()
    for path in export_files(root):
        suffix = path.suffix.lower()
        if suffix not in {".xml", ".xsd"}:
            continue
        rel = "/".join(path.relative_to(root).parts)
        text = path.read_text(encoding="utf-8")
        out.data_files += 1
        if suffix == ".xsd":
            out.roots["xsd"] += 1
        elif m := _ROOT_RE.search(text[:2000]):
            out.roots[m.group(1)] += 1
        out.uuids_by_path[rel] = len(UUID_RE.findall(text))
        out.canonical_refs += text.count('#"')
        if m and m.group(1) == "processModelHaul":
            out.nodes += len(re.findall(r'<node uuid="', text))
            out.connections += text.count("<connection>")
            out.gateway_rules += len(re.findall(r'<a:acp name="rule">', text))
            out.gateway_defaults += len(re.findall(r'<acp name="defaultNode">', text))
    return out
