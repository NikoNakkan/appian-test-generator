"""Form fields as a tester and Playwright see them, followed through child interfaces.

A screen's fields are its own plus those of the interfaces it calls, with each child's rule
inputs mapped back to the screen's own inputs (child(claimId: ri!claim) makes
the child's ri!claimId fields belong to claim). A user task's form is a call
#"<interface>"(submitted: ac!submitted, ...), which maps each process variable to a screen input.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from atg import mapdb
from atg.read.xmlutil import UUID_RE
from atg.sail import actions, fields
from atg.sail.ast import Call, Canon, SailSyntaxError, parse
from atg.sail.printer import print_node

_AC = re.compile(r"\bac!(\w+)")
_DEPTH = 4


def form_fields(con: sqlite3.Connection, sid: int, uuid: str) -> list[dict[str, Any]]:
    """Every field on the screen, with the screen inputs it belongs to and where it is defined."""
    defs = mapdb.interface_definitions(con, sid)
    names = dict(con.execute("SELECT uuid, name FROM objects WHERE snapshot_id = ?", (sid,)))
    out: list[dict[str, Any]] = []

    def walk(ui: str, mapping: dict[str, list[str]] | None, depth: int, seen: set[str]) -> None:
        if ui not in defs or ui in seen or depth > _DEPTH:
            return
        found, children = fields.find(defs[ui])
        for f in found:
            out.append(
                {
                    "kind": f.kind,
                    "label": f.label,
                    "computed_label": f.computed_label,
                    "inputs": _mapped(f.inputs, mapping),
                    "required": f.required,
                    "conditional": f.conditional,
                    "choices": f.choices,
                    "in": names.get(ui, ui),
                }
            )
        for c in children:
            child_map = {k: _mapped(vs, mapping) for k, vs in c.passes.items()}
            walk(c.interface, child_map, depth + 1, seen | {ui})

    walk(uuid, None, 0, set())
    return out


def _mapped(inputs: list[str], mapping: dict[str, list[str]] | None) -> list[str]:
    """Inputs of a child interface, as the screen's own inputs (None: this is the screen)."""
    if mapping is None:
        return inputs
    return sorted({p for i in inputs for p in mapping.get(i, [])})


def task_form(form: str) -> tuple[str, dict[str, str]]:
    """A task's form call: the interface UUID and screen input -> process variable (ac!)."""
    try:
        root = parse(form.lstrip("=")).root
    except SailSyntaxError:
        return "", {}
    if not isinstance(root, Call) or not isinstance(root.fn, Canon):
        return "", {}
    if not UUID_RE.fullmatch(root.fn.text):
        return "", {}
    return root.fn.text, {
        a.key: m.group(1)
        for a in root.args.items
        if a.key and (m := _AC.search(print_node(a.value)))
    }


def fill_labels(fields_: list[dict[str, Any]], screen_input: str) -> list[str]:
    """How a tester finds the place to enter one screen input: field labels with their kind."""
    out = []
    for f in fields_:
        if screen_input in f["inputs"]:
            label = f["label"] if f["label"] and not f["computed_label"] else ""
            choices = f" ({' / '.join(f['choices'])})" if f["choices"] else ""
            name = f"“{label}” ({f['kind']})" if label else f"the {f['kind']}{choices}"
            out.append(name)
    return list(dict.fromkeys(out))


def task_fills(con: sqlite3.Connection, sid: int, form: str) -> dict[str, list[str]]:
    """Process variable (ac! name) -> where the tester sets it: fields, or the button that does."""
    ui, inputs = task_form(form)
    if not ui:
        return {}
    found = form_fields(con, sid, ui)
    defs = mapdb.interface_definitions(con, sid)
    buttons = [a for a in actions.find(defs.get(ui, "")) if a.label and a.sets]
    out: dict[str, list[str]] = {}
    for screen_input, ac in inputs.items():
        places = fill_labels(found, screen_input)
        places += [f"button “{b.label}”" for b in buttons if screen_input in b.sets]
        out[ac] = places
    return out
