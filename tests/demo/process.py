"""A process model file from a short spec: variables, start form, and nodes with their flows.

Node spec keys: gui, type (ac/local-id), name (type name), label, to (next guiIds), and as
needed: rules [(condition, to, label)] + default (gateways), group + form + outputs (user
tasks), inputs {name: SAIL} (any node), calls (sub-process UUID).
"""

from __future__ import annotations

from typing import Any

from tests.demo.xml import HEAD, cdata

_PORT = (
    '<process_model_port xmlns="http://www.appian.com/ae/types/2009" '
    'xmlns:a="http://www.appian.com/ae/types/2009" '
    'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
)


def label(text: str) -> str:
    return f'<string-map><pair><locale country="US" lang="en" variant=""/><value>{cdata(text)}</value></pair></string-map>'


def _acp(name: str, *, value: str = "", expr: str = "", vtype: str = "xsd:string") -> str:
    v = (
        f'<a:value xsi:type="{vtype}">{value}</a:value>'
        if value
        else f'<a:value xsi:nil="true" xsi:type="{vtype}"/>'
    )
    return f'<acp name="{name}">{v}<a:expr>{cdata(expr) if expr else ""}</a:expr></acp>'


def _rules(rules: list[tuple[str, int, str]]) -> str:
    one = "".join(
        '<a:acp name="rule"><a:value xsi:type="a:Bean"><a:acps>'
        f'<a:acp name="expression"><a:value xsi:nil="true" xsi:type="xsd:boolean"/><a:expr>{cdata(cond)}</a:expr></a:acp>'
        f'<a:acp name="node"><a:value xsi:type="xsd:int">{to}</a:value><a:expr/></a:acp>'
        f'<a:acp name="label"><a:value xsi:type="xsd:string">{lab}</a:value><a:expr/></a:acp>'
        "</a:acps></a:value></a:acp>"
        for cond, to, lab in rules
    )
    return f'<acp name="rules"><a:value xsi:type="a:Bean?list"><a:acps>{one}</a:acps></a:value><a:expr/></acp>'


def form(ui: str, call: str) -> str:
    """A task or start form: Appian keeps the call as an expression and the interface uuid."""
    return (
        '<form-map><pair><locale country="US" lang="en" variant=""/><form-config><form>'
        f"<type>3</type><uiExpressionForm><expression>{cdata(call)}</expression>"
        f"<uuid>{ui}</uuid></uiExpressionForm></form></form-config></pair></form-map>"
    )


def _node(n: dict[str, Any], node_uuid: str) -> str:
    acps = "".join(_acp(k, expr=v) for k, v in n.get("inputs", {}).items())
    if "rules" in n:
        acps += _acp("defaultNode", value=str(n["default"]), vtype="xsd:int") + _rules(n["rules"])
    if "calls" in n:
        acps += _acp("pmUUID", value=n["calls"])
    outputs = "".join(f"<el>{cdata(o)}</el>" for o in n.get("outputs", []))
    who = (
        f"<assignments><assignee><value><string>{n['group']}</string></value></assignee></assignments>"
        if "group" in n
        else ""
    )
    conns = "".join(f"<connection><to>{t}</to></connection>" for t in n.get("to", []))
    return (
        f'      <node uuid="{node_uuid}"><guiId>{n["gui"]}</guiId><fname>{label(n["label"])}</fname>'
        f"<ac><local-id>{n['type']}</local-id><name>{n['name']}</name><acps>{acps}</acps>"
        f"<output-exprs>{outputs}</output-exprs></ac>{who}"
        f"<connections>{conns}</connections>{n.get('form', '')}</node>\n"
    )


def process(spec: dict[str, Any], node_uuid: Any) -> str:
    """node_uuid(gui) gives each node its own uuid."""
    pvs = "".join(
        f'      <pv name="{name}"><a:value {ns} xsi:nil="true" xsi:type="{t}"/>'
        f"<parameter>{'true' if param else 'false'}</parameter><required>false</required></pv>\n"
        for name, t, ns, param in spec["variables"]
    )
    nodes = "".join(_node(n, node_uuid(n["gui"])) for n in spec["nodes"])
    return (
        f"{HEAD}<processModelHaul>\n  {_PORT}\n    <pm>\n"
        f"      <meta><uuid>{cdata(spec['uuid'])}</uuid><name>{label(spec['name'])}</name>"
        f"<desc>{label(spec.get('desc', ''))}</desc></meta>\n"
        f"      <pvs>\n{pvs}      </pvs>\n      {spec.get('start_form', '')}\n"
        f"      <nodes>\n{nodes}      </nodes>\n    </pm>\n  </process_model_port>\n</processModelHaul>\n"
    )
