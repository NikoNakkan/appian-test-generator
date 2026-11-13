"""Entry points a user can start from: site pages and record actions (20+ layout).

site/page: staticName + uiObject@uuid (an interface, report or record list).
recordType: relatedActionCfg (staticTitleString) and recordListActionCfg (staticTitle), each
with target@uuid pointing at the process model it starts.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from atg.model import EntryPoint
from atg.read.xmlutil import attr, child, child_text, descendants, local

_ACTIONS = {
    "relatedActionCfg": ("related action", "staticTitleString", "staticDescriptionString"),
    "recordListActionCfg": ("record list action", "staticTitle", "staticDescription"),
}


def site_pages(site: Element) -> list[EntryPoint]:
    out = []
    for page in descendants(site, "page"):
        ui = child(page, "uiObject")
        target = attr(ui, "uuid") if ui is not None else ""
        if target:
            out.append(
                EntryPoint(
                    "site page", child_text(page, "staticName"), target, child_text(page, "urlStub")
                )
            )
    return out


def record_actions(record_type: Element) -> list[EntryPoint]:
    out = []
    for el in record_type.iter():
        spec = _ACTIONS.get(local(el.tag))
        if spec is None:
            continue
        kind, title_tag, desc_tag = spec
        target = child(el, "target")
        uuid = attr(target, "uuid") if target is not None else ""
        if uuid:
            out.append(EntryPoint(kind, child_text(el, title_tag), uuid, child_text(el, desc_tag)))
    return out
