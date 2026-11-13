"""Form fields a person fills in: what Playwright finds by label.

For each input component (a!textField, #"SYSTEM_SYSRULES_dropdownField_v1", ...): its kind as
a person sees it, its label (a literal, or the tidied expression when computed), the rule inputs
it shows or saves into (ri!x), and whether it is required or only shown sometimes. Calls to
child interfaces are returned too, so a ri! value can be followed into the child's own fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from atg.read.xmlutil import UUID_RE
from atg.sail.ast import Call, Canon, Name, Node, SailSyntaxError, Str, parse
from atg.sail.printer import print_node
from atg.sail.walk import keyword, nodes, plain_name

KINDS = {
    "textfield": "text box",
    "paragraphfield": "text area",
    "integerfield": "number box",
    "floatingpointfield": "number box",
    "decimalfield": "number box",
    "datefield": "date picker",
    "datetimefield": "date and time picker",
    "dropdownfield": "dropdown",
    "multipledropdownfield": "multi-select dropdown",
    "radiobuttonfield": "radio buttons",
    "checkboxfield": "checkboxes",
    "fileuploadfield": "file upload",
    "pickerfieldusers": "user picker",
    "pickerfieldgroups": "group picker",
    "pickerfieldusersandgroups": "user or group picker",
    "pickerfieldcustom": "picker",
    "pickerfieldrecords": "record picker",
    "pickerfielddocuments": "document picker",
    "signaturefield": "signature",
    "switchfield": "switch",
    "togglefield": "toggle",
    "barcodefield": "barcode",
}
_SECTIONS = {"sectionlayout", "boxlayout"}
_RI = re.compile(r"\bri!(\w+)")


@dataclass
class Field:
    kind: str
    label: str
    computed_label: bool  # the label is an expression, not literal text
    inputs: list[str]  # rule inputs it shows or saves into
    required: bool
    conditional: bool  # has showWhen: only there sometimes
    choices: list[str] = field(default_factory=list)  # literal choiceLabels, first few


@dataclass
class ChildCall:
    interface: str  # UUID
    passes: dict[str, list[str]] = field(default_factory=dict)  # child input -> parent inputs


def find(source: str) -> tuple[list[Field], list[ChildCall]]:
    try:
        root = parse(source).root
    except SailSyntaxError:
        return [], []
    fields, children = [], []
    sections = _section_titles(root)
    for n in nodes(root):
        if not isinstance(n, Call):
            continue
        name = plain_name(n.fn)
        if name in KINDS:
            f = _field(n, KINDS[name])
            if not f.label and (section := sections.get(id(n))):
                f.label = section  # an unlabelled field takes its section's title
            fields.append(f)
        elif isinstance(n.fn, Canon) and UUID_RE.fullmatch(n.fn.text):
            passes = {
                a.key: sorted(set(_RI.findall(print_node(a.value))))
                for a in n.args.items
                if a.key and _RI.search(print_node(a.value))
            }
            if passes:
                children.append(ChildCall(n.fn.text, passes))
    return fields, children


def _field(call: Call, kind: str) -> Field:
    label = keyword(call, "label")
    literal = isinstance(label, Str)
    text = label.text[1:-1].replace('""', '"') if isinstance(label, Str) else ""
    if label is not None and not literal:
        text = print_node(label)
    bound = " ".join(print_node(v) for k in ("value", "saveInto") if (v := keyword(call, k)))
    required = keyword(call, "required")
    return Field(
        kind=kind,
        label=text,
        computed_label=label is not None and not literal,
        inputs=sorted(set(_RI.findall(bound))),
        required=_truthy(required),
        conditional=keyword(call, "showWhen") is not None,
        choices=[x.text[1:-1] for x in nodes(c) if isinstance(x, Str)][:6]
        if (c := keyword(call, "choiceLabels")) is not None
        else [],
    )


def _section_titles(root: Node) -> dict[int, str]:
    """Each node inside a titled section or box layout -> the nearest title above it."""
    out: dict[int, str] = {}
    for n in nodes(root):
        if isinstance(n, Call) and plain_name(n.fn) in _SECTIONS:
            title = keyword(n, "label")
            if isinstance(title, Str) and title.text.strip('"'):
                for inner in nodes(n):
                    out[id(inner)] = title.text[1:-1].replace('""', '"')
    return out


def _truthy(n: Node | None) -> bool:
    if isinstance(n, Name):
        return n.text == "true"
    return isinstance(n, Call) and plain_name(n.fn) == "true"
