"""Content hash that ignores what changes on every save (versionUuid, history)."""

from __future__ import annotations

import copy
import hashlib
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from atg.read.xmlutil import local

_VOLATILE_TAGS = frozenset({"versionUuid", "history"})


def content_hash(root: Element) -> str:
    clean = copy.deepcopy(root)
    _strip(clean)
    canonical = ET.canonicalize(ET.tostring(clean, encoding="unicode"), strip_text=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strip(elem: Element) -> None:
    for c in list(elem):
        if local(c.tag) in _VOLATILE_TAGS:
            elem.remove(c)
        else:
            _strip(c)
    for key in [k for k in elem.attrib if local(k) == "versionUuid"]:
        del elem.attrib[key]
