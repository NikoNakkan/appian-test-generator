"""Namespace-agnostic helpers. Appian mixes default and prefixed namespaces: match local names."""

from __future__ import annotations

import re
from collections.abc import Iterator
from xml.etree.ElementTree import Element

# `_a-<uuid>_<n>` (content), `_e-<uuid>_<n>` (groups) or a plain 36-char UUID.
# The prefixed form is tried first so its inner UUID is not counted twice.
UUID_RE = re.compile(
    r"_[a-z]-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_\d+"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(elem: Element, name: str) -> Element | None:
    for c in elem:
        if local(c.tag) == name:
            return c
    return None


def child_text(elem: Element, name: str) -> str:
    c = child(elem, name)
    return (c.text or "").strip() if c is not None else ""


def attr(elem: Element, name: str) -> str:
    for k, v in elem.attrib.items():
        if local(k) == name:
            return v
    return ""


def descendants(elem: Element, name: str) -> Iterator[Element]:
    for e in elem.iter():
        if local(e.tag) == name:
            yield e


def first_string_map_value(elem: Element | None) -> str:
    """Localised names are <string-map><pair><value>; return the first non-empty one."""
    if elem is None:
        return ""
    for v in descendants(elem, "value"):
        if v.text and v.text.strip():
            return v.text.strip()
    return ""
