"""Layer 3 engine: every feasible path through one process model.

A path is one combination of choices at the XOR/complex gateways it reaches. Everything else
is followed: an AND split runs all its branches, and a node reached a second time by a forward
edge is a merge (the path already has it). A loop (back edge) is followed at most LOOP_CAP
times, which gives the 0 / 1 / many cases. A path whose choices contradict each other, with no
node in between that could change the variables involved, is infeasible and dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# XOR, complex and OR. An OR gateway can take several branches at once; each option is
# still tested on its own, which covers every branch.
GATEWAYS = frozenset({"core.3", "core.4", "core.5"})
STARTS = frozenset({"core.0"})
ENDS = frozenset({"core.1"})
LOOP_CAP = 1
MAX_PATHS = 20_000  # default cap per process; `atg ingest --max-paths` changes it
_PV = re.compile(r"pv!(\w+)")
# Calls to app rules, queries or integrations can return something different each time.
_UNSTABLE = re.compile(r'#"(?:_[a-z]-|[0-9a-fA-F]{8}-)|rule!|query|integration|now\(|today\(')


def stable(condition: str) -> bool:
    """True when a condition depends only on process variables and constants."""
    return bool(_PV.search(condition)) and not _UNSTABLE.search(condition)


@dataclass(frozen=True)
class Node:
    gui: int
    type_id: str
    label: str
    writes: tuple[str, ...] = ()
    calls: str = ""
    assignees: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    to: int
    condition: str
    label: str


@dataclass
class Graph:
    nodes: dict[int, Node]
    succ: dict[int, list[int]]
    rules: dict[int, list[Rule]]  # gateway gui -> its rules, in evaluation order
    defaults: dict[int, int]  # gateway gui -> default target


@dataclass(frozen=True)
class Decision:
    gateway: int
    to: int
    rule: str  # the rule label, or "default"
    must_be_true: str  # condition of the chosen rule ("" for default)
    must_be_false: tuple[str, ...]  # conditions of the rules before it


@dataclass
class Path:
    steps: list[int] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    loops: int = 0


@dataclass
class Result:
    paths: list[Path]
    infeasible: int
    truncated: bool
    back_edges: set[tuple[int, int]]


def starts(g: Graph) -> list[int]:
    found = [n for n, node in g.nodes.items() if node.type_id in STARTS]
    if found:
        return found
    targets = {t for ts in g.succ.values() for t in ts}
    return [n for n in g.nodes if n not in targets]


def back_edges(g: Graph) -> set[tuple[int, int]]:
    """Edges that return to a node still on the depth-first stack: the loops."""
    found: set[tuple[int, int]] = set()
    state: dict[int, int] = {}  # 1 = on stack, 2 = done
    for root in starts(g):
        stack = [(root, iter(g.succ.get(root, [])))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                found.add((node, nxt))
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(g.succ.get(nxt, []))))
    return found


def gateway_options(g: Graph, gateway: int, nexts: list[int]) -> list[Decision]:
    """Each rule is its own option, even when two rules lead to the same node: they need
    different data. Rules are tried in order, so a rule also needs the ones before it false."""
    rules = [r for r in g.rules.get(gateway, []) if r.to in nexts]
    options = [
        Decision(
            gateway, r.to, r.label or "rule", r.condition, tuple(x.condition for x in rules[:i])
        )
        for i, r in enumerate(rules)
    ]
    covered = {r.to for r in rules}
    default = g.defaults.get(gateway)
    if default in nexts:
        options.append(Decision(gateway, default, "default", "", tuple(r.condition for r in rules)))
        covered.add(default)
    # Connections no rule or default explains: follow them without assuming anything.
    options += [Decision(gateway, t, "unconditional", "", ()) for t in nexts if t not in covered]
    return options


def enumerate_paths(g: Graph, max_paths: int | None = None) -> Result:
    cap = MAX_PATHS if max_paths is None else max_paths
    loops = back_edges(g)
    out: list[Path] = []
    infeasible = 0
    truncated = False

    # Work items: (pending (from, to) edges, visited, loop counts, path, known condition values)
    work: list[
        tuple[list[tuple[int, int]], set[int], dict[tuple[int, int], int], Path, dict[str, bool]]
    ] = [([(-1, s)], set(), {}, Path(), {}) for s in starts(g)]
    while work:
        if len(out) >= cap:
            truncated = True
            break
        pending, visited, counts, path, known = work.pop()
        forked = False
        while pending:
            edge = pending.pop()
            node = edge[1]
            if edge in loops:
                if counts.get(edge, 0) >= LOOP_CAP:
                    continue
                counts[edge] = counts.get(edge, 0) + 1
                path.loops += 1
            elif node in visited:
                continue  # a merge: this path already passed here
            visited.add(node)
            path.steps.append(node)
            _forget_written(known, g.nodes[node].writes if node in g.nodes else ())
            nexts = g.succ.get(node, [])
            if node in g.nodes and g.nodes[node].type_id in GATEWAYS and len(nexts) > 1:
                for d in gateway_options(g, node, nexts):
                    k = dict(known)
                    if not _assume(k, d):
                        infeasible += 1
                        continue
                    p = Path(list(path.steps), [*path.decisions, d], path.loops)
                    work.append(([*pending, (node, d.to)], set(visited), dict(counts), p, k))
                forked = True
                break
            pending.extend((node, t) for t in reversed(nexts))
        if not forked:
            out.append(path)
    return Result(out, infeasible, truncated, loops)


def _assume(known: dict[str, bool], d: Decision) -> bool:
    """Record what this choice requires; False when it contradicts an earlier choice."""
    wanted = [(c, False) for c in d.must_be_false] + (
        [(d.must_be_true, True)] if d.must_be_true else []
    )
    for cond, value in wanted:
        if not stable(cond):
            continue
        key = " ".join(cond.split())
        if known.get(key, value) != value:
            return False
        known[key] = value
    return True


def _forget_written(known: dict[str, bool], writes: tuple[str, ...]) -> None:
    """A node that sets a variable makes earlier conclusions about it unreliable."""
    if not writes:
        return
    for cond in [c for c in known if set(_PV.findall(c)) & set(writes)]:
        del known[cond]
