"""What Designer shows for each object and process node, for the read-only viewer.

Object details: description, rule inputs, constant value, record fields and views, process
variables, and for everything else a generic list of settings. Node details: every setting
(acp) with its value or expression and the variable it saves into, outputs, and the form.
"""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

from atg.read.records import record_type, short_type
from atg.read.xmlutil import attr, child, child_text, descendants, local

Details = dict[str, Any]

# Never shown as settings: housekeeping, or shown in a dedicated section.
_SKIP = frozenset(
    {
        "visibility",
        "roleMap",
        "history",
        "versionUuid",
        "uuid",
        "parentUuid",
        "name",
        "description",
        "definition",
        "namedTypedValue",
        "typedValue",
        "field",
        "relatedActionCfg",
        "recordListActionCfg",
        "preferredEditor",
        "offlineEnabled",
        "metadataExpr",
    }
)
_GATEWAY_INTERNALS = frozenset({"rules", "defaultNode", "fired", "arrivedNodes"})
# Containers that add nothing to a setting's label.
_WRAPPERS = frozenset({"Dictionary", "item", "value", "sharedConfigParameters", "configParameters"})
_DEBUG_MARK = "/*41707069616E-GEN-DEBUG*/"
_MAX_SETTINGS = 150


def object_details(inner: Element, obj_type: str, pm: Element | None = None) -> Details:
    d: Details = {"description": child_text(inner, "description")}
    inputs = [_input(nt) for nt in inner if local(nt.tag) == "namedTypedValue"]
    if inputs:
        d["inputs"] = inputs
    if obj_type == "constant":
        d["constant"] = _constant(child(inner, "typedValue"))
    elif obj_type == "recordType":
        d.update(record_type(inner))
        d["views"] = [
            {
                "name": child_text(v, "nameExpr"),
                "expression": child_text(v, "uiExpr"),
                "stub": child_text(v, "urlStub"),
                "visibility": child_text(v, "visibilityExpr"),
            }
            for v in descendants(inner, "detailViewCfg")
        ]
    elif obj_type == "processModel" and pm is not None:
        d["variables"] = _variables(pm)
        meta = child(pm, "meta")
        desc = child(meta, "desc") if meta is not None else None
        d["description"] = d["description"] or _first_value(desc)
    if obj_type == "site":
        d["pages"] = site_pages(inner)
    if obj_type not in {"rule", "interface", "constant", "processModel"}:
        d["settings"] = settings(inner)
    return d


def site_pages(site: Element) -> list[Details]:
    """Each page with where it opens and who may see it (the gate, as written)."""
    out = []
    for page in descendants(site, "page"):
        ui = child(page, "uiObject")
        out.append(
            {
                "name": child_text(page, "staticName"),
                "stub": child_text(page, "urlStub"),
                "target": attr(ui, "uuid") if ui is not None else "",
                "visibility": child_text(page, "visibilityExpr"),
            }
        )
    return out


def xsd_fields(schema: Element) -> list[Details]:
    """Fields of a data type: the xsd:elements of its complexType."""
    ctype = child(schema, "complexType")
    out = []
    for el in descendants(ctype, "element") if ctype is not None else []:
        many = el.get("maxOccurs") == "unbounded"
        kind = short_type(el.get("type", ""))
        out.append(
            {
                "name": el.get("name", ""),
                "type": f"{kind} (list)" if many else kind,
                "nullable": el.get("nillable") == "true",
            }
        )
    return out


def settings(inner: Element) -> list[Details]:
    """Leaf values under an object, labelled by their tag path; expressions flagged as code."""
    out: list[Details] = []

    def walk(e: Element, path: list[str]) -> None:
        for c in e:
            tag = local(c.tag)
            if tag in _SKIP or len(out) >= _MAX_SETTINGS:
                continue
            text = (c.text or "").strip()
            if len(c) == 0 and text:
                is_code = (
                    tag in {"expression", "expr"}
                    or attr(c, "type").endswith("Expression")
                    or (tag.endswith("Expr") and text not in {"true", "false"})
                )
                where = [p for p in path[-1:] if p not in _WRAPPERS]
                out.append({"label": " > ".join([*where, tag]), "value": text, "code": is_code})
            elif len(c):
                walk(c, [*path, tag])

    walk(inner, [])
    return out


def node_details(node: Element, ac: Element | None) -> Details:
    d: Details = {"inputs": [], "outputs": [], "form": ""}
    if ac is None:
        return d
    for block in ("acps", "custom-params"):
        container = child(ac, block)
        for acp in container if container is not None else []:
            if acp.get("name") not in _GATEWAY_INTERNALS and (tree := _acp(acp)):
                d["inputs"].append(tree)
    outputs = child(ac, "output-exprs")
    d["outputs"] = [
        (el.text or "").strip()
        for el in (outputs if outputs is not None else [])
        if (el.text or "").strip()
    ]
    # The task's screen is form-map > ... > uiExpressionForm > expression (one per locale, the
    # same interface each time). Older nodes keep an inline layout as a node expression instead.
    forms = [
        (e.text or "").replace(_DEBUG_MARK, "").strip()
        for f in descendants(node, "uiExpressionForm")
        for e in descendants(f, "expression")
    ]
    inline = [
        text
        for e in descendants(node, "expression")
        if (text := (e.text or "").replace(_DEBUG_MARK, "").strip()).startswith("=")
        and "Layout" in text
    ]
    d["form"] = next((t for t in forms + inline if t), "")
    return d


def _acp(acp: Element) -> Details | None:
    """One node setting: name, literal value or expression, saves-into, nested settings."""
    if child_text(acp, "hidden-from-designer") == "true":
        return None
    value = child(acp, "value")
    nested = child(value, "acps") if value is not None else None
    kids = [k for k in (_acp(x) for x in (nested if nested is not None else [])) if k]
    literal = (value.text or "").strip() if value is not None and nested is None else ""
    expr = child_text(acp, "expr")
    saves = child_text(acp, "assign-to-pv")
    if not (literal or expr or saves or kids):
        return None
    return {
        "name": acp.get("name") or attr(acp, "name"),
        "value": literal,
        "expr": expr,
        "saves_into": saves,
        "type": short_type(attr(value, "type") if value is not None else ""),
        "children": kids,
    }


def _input(nt: Element) -> Details:
    t = child(nt, "type")
    return {
        "name": child_text(nt, "name"),
        "description": child_text(nt, "description"),
        "type": short_type(child_text(t, "name") if t is not None else ""),
    }


def _constant(typed: Element | None) -> Details:
    if typed is None:
        return {}
    t = child(typed, "type")
    values = [(v.text or "").strip() or attr(v, "id") for v in typed if local(v.tag) == "value"]
    return {"type": short_type(child_text(t, "name") if t is not None else ""), "values": values}


def _variables(pm: Element) -> list[Details]:
    pvs = child(pm, "pvs")
    out = []
    for pv in pvs if pvs is not None else []:
        value = child(pv, "value")
        out.append(
            {
                "name": pv.get("name", ""),
                "type": short_type(attr(value, "type") if value is not None else ""),
                "parameter": child_text(pv, "parameter") == "true",
                "required": child_text(pv, "required") == "true",
                "initial": (value.text or "").strip() if value is not None else "",
            }
        )
    return out


def _first_value(e: Element | None) -> str:
    for v in descendants(e, "value") if e is not None else []:
        if (v.text or "").strip():
            return (v.text or "").strip()
    return ""
