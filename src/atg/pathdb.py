"""Test paths as stored in the map, written and read through this one module.

A path row keeps only what belongs to that path: `steps` (node gui ids, in order, as compact
JSON) and `choices`, `[[gateway, option], ...]`, where option is the position of the chosen
branch in `path_engine.gateway_options` for that gateway. Everything else is a fact of the
process and is rebuilt on read from `nodes` and `flows`: each choice's rule label and
conditions, the processes the path calls, its user tasks and who gets them. That keeps a row
at tens of bytes instead of about a kilobyte of repeated condition text.

Maps imported before this format have `choices` empty and the full JSON in `decisions`,
`calls` and `tasks`; those rows are read as they are.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from atg.layers.path_engine import Decision, Graph, Node, Path, Rule, gateway_options

USER_TASK = "internal.17"
_COLUMNS = "path_no, steps, choices, decisions, calls, tasks, loops"


@dataclass
class StoredPath:
    no: int
    steps: list[int]
    decisions: list[dict[str, Any]]  # gateway, to, rule, must_be_true, must_be_false
    calls: list[str]  # processes this path starts, sorted
    tasks: list[list[Any]]  # [node, [assignees]] per user task, in order
    loops: int


def load_graph(con: sqlite3.Connection, sid: int, pm: str) -> Graph:
    nodes = {
        gui: Node(
            gui,
            type_id,
            label or type_name,
            tuple(json.loads(w or "[]")),
            calls or "",
            tuple(json.loads(a or "[]")),
        )
        for gui, type_id, type_name, label, w, calls, a in con.execute(
            "SELECT gui_id, type_id, type_name, label, writes, calls, assignees FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    }
    succ: dict[int, list[int]] = {}
    rules: dict[int, list[Rule]] = {}
    defaults: dict[int, int] = {}
    for a, b, kind, label, cond in con.execute(
        "SELECT from_gui, to_gui, kind, label, condition FROM flows "
        "WHERE snapshot_id = ? AND pm_uuid = ? ORDER BY rowid",
        (sid, pm),
    ):
        if kind == "connection" and b in nodes and b not in succ.get(a, []):
            succ.setdefault(a, []).append(b)
        elif kind == "gateway_rule":
            rules.setdefault(a, []).append(Rule(b, cond or "", label or ""))
        elif kind == "gateway_default":
            defaults[a] = b
    return Graph(nodes, succ, rules, defaults)


def _compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def rows(sid: int, pm: str, g: Graph, paths: list[Path]) -> Iterator[tuple[object, ...]]:
    """The `paths` rows of one process in the compact format (column order of `INSERT_SQL`)."""
    index: dict[int, dict[Decision, int]] = {}
    for no, p in enumerate(paths, 1):
        choices = []
        for d in p.decisions:
            if d.gateway not in index:
                found = gateway_options(g, d.gateway, g.succ.get(d.gateway, []))
                index[d.gateway] = {o: i for i, o in reversed(list(enumerate(found)))}
            choices.append([d.gateway, index[d.gateway][d]])
        yield (sid, pm, no, _compact(p.steps), _compact(choices), p.loops)


INSERT_SQL = (
    "INSERT INTO paths (snapshot_id, pm_uuid, path_no, steps, choices, loops) VALUES (?,?,?,?,?,?)"
)


def _decision(d: Decision) -> dict[str, Any]:
    return {
        "gateway": d.gateway,
        "to": d.to,
        "rule": d.rule,
        "must_be_true": d.must_be_true,
        "must_be_false": list(d.must_be_false),
    }


class _Rebuilder:
    """Rebuilds the derived parts of compact rows of one process, caching per gateway."""

    def __init__(self, g: Graph) -> None:
        self.g = g
        self.options: dict[int, list[dict[str, Any]]] = {}

    def decisions(self, choices: list[list[int]]) -> list[dict[str, Any]]:
        out = []
        for gateway, option in choices:
            if gateway not in self.options:
                found = gateway_options(self.g, gateway, self.g.succ.get(gateway, []))
                self.options[gateway] = [_decision(d) for d in found]
            out.append(self.options[gateway][option])
        return out

    def calls(self, steps: list[int]) -> list[str]:
        nodes = self.g.nodes
        return sorted({nodes[s].calls for s in steps if s in nodes and nodes[s].calls})

    def tasks(self, steps: list[int]) -> list[list[Any]]:
        nodes = self.g.nodes
        return [
            [s, list(nodes[s].assignees)]
            for s in steps
            if s in nodes and nodes[s].type_id == USER_TASK
        ]


def _read_rows(
    con: sqlite3.Connection, sid: int, pm: str, rows: list[tuple[Any, ...]]
) -> list[StoredPath]:
    rebuild: _Rebuilder | None = None
    out = []
    for no, steps_raw, choices, decisions, calls, tasks, loops in rows:
        steps = json.loads(steps_raw)
        if choices is None:  # imported before the compact format
            out.append(
                StoredPath(
                    no, steps, json.loads(decisions), json.loads(calls), json.loads(tasks), loops
                )
            )
            continue
        if rebuild is None:
            rebuild = _Rebuilder(load_graph(con, sid, pm))
        out.append(
            StoredPath(
                no,
                steps,
                rebuild.decisions(json.loads(choices)),
                rebuild.calls(steps),
                rebuild.tasks(steps),
                loops,
            )
        )
    return out


def read(con: sqlite3.Connection, sid: int, pm: str) -> list[StoredPath]:
    """Every path of one process, in path order."""
    rows = con.execute(
        f"SELECT {_COLUMNS} FROM paths WHERE snapshot_id = ? AND pm_uuid = ? ORDER BY path_no",
        (sid, pm),
    ).fetchall()
    return _read_rows(con, sid, pm, rows)


def read_one(con: sqlite3.Connection, sid: int, pm: str, no: int) -> StoredPath | None:
    rows = con.execute(
        f"SELECT {_COLUMNS} FROM paths WHERE snapshot_id = ? AND pm_uuid = ? AND path_no = ?",
        (sid, pm, no),
    ).fetchall()
    found = _read_rows(con, sid, pm, rows)
    return found[0] if found else None


def read_all(con: sqlite3.Connection, sid: int) -> Iterator[tuple[str, list[StoredPath]]]:
    """Every process of a snapshot that has paths, with its paths, ordered by process uuid."""
    pms = [
        pm
        for (pm,) in con.execute(
            "SELECT DISTINCT pm_uuid FROM paths WHERE snapshot_id = ? ORDER BY pm_uuid", (sid,)
        )
    ]
    for pm in pms:
        yield pm, read(con, sid, pm)
