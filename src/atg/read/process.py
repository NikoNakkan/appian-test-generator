"""Process model nodes, connections and gateway rules (20+ layout).

pm/nodes/node: guiId, @uuid, fname (label), ac/local-id (type), ac/name,
connections/connection/to (target guiId), and for gateways ac/acps/acp[@name=rules]
-> acp[@name=rule] -> acp expression / node / label, plus acp[@name=defaultNode].
"""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

from atg.model import Flow, FlowKind, ProcessNode
from atg.read import details
from atg.read.known import GATEWAY_TYPES
from atg.read.xmlutil import attr, child, child_text, descendants, first_string_map_value, local


def find_pm(root: Element) -> Element | None:
    port = child(root, "process_model_port")
    return child(port, "pm") if port is not None else None


def pm_identity(pm: Element) -> tuple[str, str]:
    meta = child(pm, "meta")
    if meta is None:
        return "", ""
    return child_text(meta, "uuid"), first_string_map_value(child(meta, "name"))


def node_details(pm: Element) -> dict[int, dict[str, Any]]:
    """Designer's node properties for every node, by guiId (for the read-only viewer)."""
    container = child(pm, "nodes")
    return {
        int(child_text(node, "guiId") or -1): details.node_details(node, child(node, "ac"))
        for node in (container if container is not None else [])
        if local(node.tag) == "node"
    }


def extract(pm: Element) -> tuple[list[ProcessNode], list[Flow]]:
    nodes: list[ProcessNode] = []
    flows: list[Flow] = []
    container = child(pm, "nodes")
    for node in container if container is not None else []:
        if local(node.tag) != "node":
            continue
        gui = int(child_text(node, "guiId") or -1)
        ac = child(node, "ac")
        type_id = child_text(ac, "local-id") if ac is not None else ""
        nodes.append(
            ProcessNode(
                gui_id=gui,
                node_uuid=attr(node, "uuid"),
                type_id=type_id,
                type_name=child_text(ac, "name") if ac is not None else "",
                label=first_string_map_value(child(node, "fname")),
                writes=_writes(ac),
                calls=_called_process(ac),
                assignees=_assignees(node),
            )
        )
        flows.extend(_connections(node, gui))
        if ac is not None and type_id in GATEWAY_TYPES:
            flows.extend(_gateway_rules(ac, gui))
    return nodes, flows


def _writes(ac: Element | None) -> tuple[str, ...]:
    """Process variables a node sets: output-exprs entries look like `submitted:ac!submitted`."""
    if ac is None:
        return ()
    names = []
    outputs = child(ac, "output-exprs")
    for el in outputs if outputs is not None else []:
        target = (el.text or "").split(":", 1)[0]
        name = target.split("[", 1)[0].split(".", 1)[0].strip().removeprefix("pv!")
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _called_process(ac: Element | None) -> str:
    """UUID of the process a sub-process node starts (acp pmUUID)."""
    acps = child(ac, "acps") if ac is not None else None
    for acp in acps if acps is not None else []:
        if acp.get("name") == "pmUUID":
            return child_text(acp, "value")
    return ""


def _assignees(node: Element) -> tuple[str, ...]:
    """Who a user task goes to: group UUIDs, user names or assignment expressions."""
    block = child(node, "assignments")
    if block is None:
        return ()
    return tuple(
        (v.text or "").strip()
        for a in block
        if local(a.tag) == "assignee"
        for v in descendants(a, "string")
        if (v.text or "").strip()
    )


def _connections(node: Element, gui: int) -> list[Flow]:
    out = []
    conns = child(node, "connections")
    for c in conns if conns is not None else []:
        if local(c.tag) != "connection":
            continue
        label = first_string_map_value(child(c, "label")) or child_text(c, "flowLabel")
        out.append(Flow(gui, int(child_text(c, "to") or -1), FlowKind.CONNECTION, label))
    return out


def _gateway_rules(ac: Element, gui: int) -> list[Flow]:
    out = []
    acps = child(ac, "acps")
    for acp in acps if acps is not None else []:
        name = acp.get("name")
        if name == "defaultNode":
            target = _acp_value(acp)
            if target.lstrip("-").isdigit():
                out.append(Flow(gui, int(target), FlowKind.GATEWAY_DEFAULT))
        elif name == "rules":
            out.extend(
                _rule(rule, gui)
                for rule in descendants(acp, "acp")
                if rule.get("name") == "rule" or attr(rule, "name") == "rule"
            )
    return out


def _rule(rule: Element, gui: int) -> Flow:
    parts = {
        (p.get("name") or attr(p, "name")): p for p in descendants(rule, "acp") if p is not rule
    }
    expr = parts.get("expression")
    condition = child_text(expr, "expr") if expr is not None else ""
    node = parts.get("node")
    target = _acp_value(node) if node is not None else ""
    label = parts.get("label")
    return Flow(
        gui,
        int(target) if target.lstrip("-").isdigit() else -1,
        FlowKind.GATEWAY_RULE,
        _acp_value(label) if label is not None else "",
        condition,
    )


def _acp_value(acp: Element) -> str:
    return child_text(acp, "value")
