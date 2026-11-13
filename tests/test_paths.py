"""Path engine on small hand-made processes: one test per tricky shape."""

from __future__ import annotations

from atg.layers.path_engine import Graph, Node, Rule, enumerate_paths

START, END, XOR, AND, TASK = "core.0", "core.1", "core.4", "core.2", "internal.16"


def graph(
    nodes: dict[int, str],
    edges: list[tuple[int, int]],
    rules: dict[int, list[tuple[int, str]]] | None = None,
    defaults: dict[int, int] | None = None,
    writes: dict[int, tuple[str, ...]] | None = None,
) -> Graph:
    succ: dict[int, list[int]] = {}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    return Graph(
        {n: Node(n, t, f"n{n}", (writes or {}).get(n, ())) for n, t in nodes.items()},
        succ,
        {g: [Rule(to, c, "yes") for to, c in rs] for g, rs in (rules or {}).items()},
        defaults or {},
    )


def test_xor_gives_one_path_per_option() -> None:
    g = graph(
        {0: START, 1: XOR, 2: TASK, 3: END},
        [(0, 1), (1, 2), (1, 3), (2, 3)],
        {1: [(2, "=pv!send")]},
        {1: 3},
    )
    r = enumerate_paths(g)
    assert sorted(p.steps for p in r.paths) == [[0, 1, 2, 3], [0, 1, 3]]
    default = next(p for p in r.paths if p.steps == [0, 1, 3]).decisions[0]
    assert (default.rule, default.must_be_false) == ("default", ("=pv!send",))


def test_and_split_runs_both_branches_in_one_path() -> None:
    g = graph(
        {0: START, 1: AND, 2: TASK, 3: TASK, 4: AND, 5: END},
        [(0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5)],
    )
    r = enumerate_paths(g)
    assert len(r.paths) == 1
    assert set(r.paths[0].steps) == {0, 1, 2, 3, 4, 5}


def test_loop_runs_at_most_twice() -> None:
    g = graph(
        {0: START, 1: TASK, 2: XOR, 3: END},
        [(0, 1), (1, 2), (2, 1), (2, 3)],
        {2: [(3, "=pv!done")]},
        {2: 1},
        {1: ("done",)},
    )
    r = enumerate_paths(g)
    assert (2, 1) in r.back_edges
    assert sorted(p.loops for p in r.paths) == [0, 1]


def test_contradicting_choices_are_dropped() -> None:
    g = graph(
        {0: START, 1: XOR, 2: TASK, 3: XOR, 4: TASK, 5: END},
        [(0, 1), (1, 2), (1, 3), (2, 3), (3, 4), (3, 5), (4, 5)],
        {1: [(2, "=pv!x = 1")], 3: [(4, "=pv!x = 1")]},
        {1: 3, 3: 5},
    )
    r = enumerate_paths(g)
    assert len(r.paths) == 2 and r.infeasible == 2  # yes-then-no and no-then-yes are impossible


def test_a_write_in_between_keeps_both_choices_possible() -> None:
    g = graph(
        {0: START, 1: XOR, 2: TASK, 3: XOR, 4: TASK, 5: END},
        [(0, 1), (1, 2), (1, 3), (2, 3), (3, 4), (3, 5), (4, 5)],
        {1: [(2, "=pv!x = 1")], 3: [(4, "=pv!x = 1")]},
        {1: 3, 3: 5},
        {2: ("x",)},
    )
    assert enumerate_paths(g).infeasible == 1  # only the path skipping node 2 is constrained


def test_conditions_calling_rules_are_never_treated_as_contradictions() -> None:
    cond = '=#"_a-0000ec54-8303-8000-9d04-011c48011c48_1"(id: pv!x)'
    g = graph(
        {0: START, 1: XOR, 2: XOR, 3: END},
        [(0, 1), (1, 2), (1, 3), (2, 3), (2, 1)],
        {1: [(2, cond)], 2: [(3, cond)]},
        {1: 3, 2: 1},
    )
    assert enumerate_paths(g).infeasible == 0


def test_two_rules_to_the_same_node_are_two_options() -> None:
    g = graph(
        {0: START, 1: XOR, 2: TASK, 3: END},
        [(0, 1), (1, 2), (1, 3), (2, 3)],
        {1: [(2, "=pv!a"), (2, "=pv!b")]},
        {1: 3},
    )
    r = enumerate_paths(g)
    assert sorted(p.decisions[0].must_be_true for p in r.paths) == ["", "=pv!a", "=pv!b"]
