"""Record type facts that test data depends on, and the test inputs developers saved.

Record type (recordTypeHaul, 24+):
  field                  name, type, column (sourceFieldName), record id, computed
                         (isCustomField + customFieldExpr: Appian calculates it, never set it)
  recordRelationshipCfg  name, target record type, ONE_TO_MANY / MANY_TO_ONE / ONE_TO_ONE
  sourceConfiguration    where rows live (RDBMS_TABLE + table, EXPRESSION, ...) and sync schedule
  related/list actions   a:uuid (what urn:appian:record-action points at), title, process
Saved tests: the haul's typedValue RuleTestConfig?list, one entry per saved test, each with
ruleInputTestConfigs (nameRef + value). Assertions are kept when present.
"""

from __future__ import annotations

import json
from typing import Any
from xml.etree.ElementTree import Element

from atg.read.xmlutil import attr, child, child_text, descendants, local

Details = dict[str, Any]
_ACTIONS = {"relatedActionCfg": ("related action", "staticTitleString"),
            "recordListActionCfg": ("record list action", "staticTitle")}  # fmt: skip
_XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def short_type(t: str) -> str:
    """xsd:string -> Text, n1:EXP_Receipt?list -> EXP_Receipt (list), {ns}Integer -> Integer."""
    if not t:
        return ""
    many = t.endswith("?list")
    name = t.removesuffix("?list").rsplit("}", 1)[-1].rsplit(":", 1)[-1]
    name = {
        "string": "Text",
        "int": "Integer",
        "boolean": "Boolean",
        "double": "Decimal",
        "dateTime": "Date and time",
        "date": "Date",
    }.get(name, name)
    return f"{name} (list)" if many else name


def record_type(inner: Element) -> Details:
    return {
        "fields": fields(inner),
        "relationships": [
            {
                "uuid": child_text(r, "uuid"),
                "name": child_text(r, "relationshipName"),
                "target": child_text(r, "targetRecordTypeUuid"),
                "kind": child_text(r, "relationshipType"),
            }
            for r in descendants(inner, "recordRelationshipCfg")
        ],
        "source": _source(inner),
        "actions": [
            {
                "uuid": attr(el, "uuid"),
                "kind": _ACTIONS[local(el.tag)][0],
                "name": child_text(el, _ACTIONS[local(el.tag)][1]),
                "target": attr(t, "uuid") if (t := child(el, "target")) is not None else "",
                "visibility": child_text(el, "visibilityExpr"),
            }
            for el in inner.iter()
            if local(el.tag) in _ACTIONS
        ],
    }


def fields(record: Element) -> list[Details]:
    out = []
    for f in descendants(record, "field"):
        uuid = child_text(f, "uuid")
        if not uuid:
            continue
        out.append(
            {
                "uuid": uuid,
                "name": child_text(f, "fieldName") or child_text(f, "name"),
                "label": child_text(f, "displayName"),
                "type": short_type(child_text(f, "type")),
                "column": child_text(f, "sourceFieldName"),
                "is_id": child_text(f, "isRecordId") == "true",
                "computed": child_text(f, "isCustomField") == "true",
                "expression": child_text(f, "customFieldExpr"),
            }
        )
    return out


def _source(inner: Element) -> Details:
    src = next(descendants(inner, "sourceConfiguration"), None)
    if src is None:
        return {}
    sync = child(src, "refreshSchedule")
    schedule = json.loads(child_text(sync, "value") or "{}") if sync is not None else {}
    return {
        "kind": child_text(src, "sourceType"),
        "table": child_text(src, "friendlyName"),
        "source": child_text(src, "sourceUuid"),
        "sync": {
            "frequency": child_text(sync, "frequency"),
            "on": child_text(sync, "activated") == "true",
            "at": "{}:{} {}".format(
                schedule.get("hour", ""), schedule.get("minute", ""), schedule.get("amPM", "")
            ).strip(),
        }
        if sync is not None
        else {},
    }


def saved_tests(root: Element) -> list[Details]:
    """Test inputs saved on a rule or interface in Designer."""
    typed = child(root, "typedValue")
    kind = child(typed, "type") if typed is not None else None
    if typed is None or kind is None or "RuleTestConfig" not in child_text(kind, "name"):
        return []
    out = []
    for el in descendants(typed, "el"):
        inputs = {
            child_text(c, "nameRef"): _value(child(c, "value"))
            for c in el
            if local(c.tag) == "ruleInputTestConfigs" and child_text(c, "nameRef")
        }
        assertions = child(el, "assertions")
        out.append(
            {
                "name": child_text(el, "name"),
                "inputs": inputs,
                "has_assertions": assertions is not None and assertions.get(_XSI_NIL) != "true",
            }
        )
    return out


def _value(v: Element | None) -> str:
    """The saved value as SAIL text; null when nothing was entered."""
    if v is None or v.get(_XSI_NIL) == "true":
        return "null"
    text = (v.text or "").strip()
    if v.get(_XSI_TYPE, "").endswith(("string", "String")):
        return '"' + text.replace('"', '""') + '"'
    return text or "null"
