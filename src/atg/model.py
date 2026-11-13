"""Core model. Stable across Appian versions: readers produce these, later layers consume them."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RefKind(StrEnum):
    """How one object points at something else."""

    SAIL = "sail"  # #"<uuid>"(...) inside an expression
    SAIL_NAME = "sail_name"  # #"SomeName"(...) — reference by name
    PLATFORM = "platform"  # #"SYSTEM_SYSRULES_x" — built-in function, never resolved
    RECORD_TYPE = "record_type"  # #"urn:appian:record-type|record-field:v1:<rt>/..."
    TYPE = "type"  # type!{ns}Name or <type><name>/<namespace>
    XML = "xml"  # UUID in an XML tag/attribute (parentUuid, groupUuid, ...)
    SELF = "self"  # #"..." pointing at the object itself (recursion, own record fields)


class UuidUse(StrEnum):
    """Why a UUID token appears in a file. Every token in the raw text gets exactly one."""

    SELF = "self"
    VERSION = "version"  # versionUuid / history — changes on every save, not a reference
    INTERNAL = "internal"  # id defined inside the same file (process node, record field)
    REFERENCE = "reference"
    URN_PART = "urn_part"  # the field/relationship part of a record-field urn


class UnknownKind(StrEnum):
    PARSE_ERROR = "parse_error"
    HAUL_ROOT = "haul_root"
    CONTENT_SUBTYPE = "content_subtype"
    NODE_TYPE = "node_type"
    FILE = "file"
    NO_UUID = "no_uuid"


@dataclass(frozen=True)
class Reference:
    source: str
    kind: RefKind
    target: str
    context: str  # tag or @attribute where it was found, or the full urn


@dataclass(frozen=True)
class UuidToken:
    token: str
    use: UuidUse


@dataclass(frozen=True)
class ProcessNode:
    gui_id: int
    node_uuid: str
    type_id: str  # ac/local-id, e.g. core.4
    type_name: str  # ac/name, e.g. XOR
    label: str
    writes: tuple[str, ...] = ()  # process variables this node sets
    calls: str = ""  # UUID of the process a sub-process node starts
    assignees: tuple[str, ...] = ()  # groups, users or expressions a user task goes to


class FlowKind(StrEnum):
    CONNECTION = "connection"
    GATEWAY_RULE = "gateway_rule"
    GATEWAY_DEFAULT = "gateway_default"


@dataclass(frozen=True)
class Flow:
    from_gui: int
    to_gui: int
    kind: FlowKind
    label: str = ""
    condition: str = ""


@dataclass(frozen=True)
class EntryPoint:
    """Somewhere a user starts: a site page or a record action."""

    kind: str  # site page, related action, record list action
    name: str  # the title Appian shows, e.g. "New claim"
    target: str  # UUID of the interface / report / process it opens
    description: str = ""


@dataclass
class AppObject:
    uuid: str
    type: str  # canonical type, e.g. rule, interface, processModel, datatype
    name: str
    path: str  # relative to the export root
    haul_root: str  # e.g. contentHaul; "xsd" for datatypes
    content_hash: str = ""
    definition: str = ""  # SAIL source of rules, interfaces and decisions
    entry_points: list[EntryPoint] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)  # what Designer shows (viewer only)
    node_details: dict[int, dict[str, Any]] = field(default_factory=dict)  # by node guiId
    internal_ids: set[str] = field(default_factory=set)
    references: list[Reference] = field(default_factory=list)
    tokens: list[UuidToken] = field(default_factory=list)
    nodes: list[ProcessNode] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)


@dataclass(frozen=True)
class Unknown:
    kind: UnknownKind
    value: str
    path: str


@dataclass
class Snapshot:
    source: str
    appian_version: str
    reader: str
    objects: list[AppObject] = field(default_factory=list)
    unknowns: list[Unknown] = field(default_factory=list)
    binary_files: list[str] = field(default_factory=list)
