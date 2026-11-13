"""SAIL grammar, round-trip printing and decision points, on small hand-written sources."""

from __future__ import annotations

import pytest

from atg.sail.ast import SailSyntaxError, parse
from atg.sail.branches import find, function_name
from atg.sail.printer import normalise, to_text

RT = "91b70937-07ac-4038-be6e-fe2336bc5559"
FIELD = "561f08bd-d537-4da3-863d-576c3396b558"

SOURCES = [
    "if(ri!amount > 50000, true, false)",
    "=pv!submitted",
    "=if(a!isNullOrEmpty(pv!comments), false, true)",
    'a!localVariables(local!x: {a: 1, b: "say ""hi"""}, local!x.a)',
    '#"SYSTEM_SYSRULES_forEach"(items: ri!list, expression: fv!item * 2,)',
    f'ri!op[#"urn:appian:record-field:v1:{RT}/{FIELD}"]',
    f'ri!op.[#"urn:appian:record-field:v1:{RT}/{FIELD}"]',
    f'{{#"urn:appian:record-field:v1:{RT}/{FIELD}": ""}}',
    "#\"SYSTEM_SYSRULES_dd_dd\"('hitPolicy': \"UNIQUE\", 'inputs': {})",
    "cast('type!{urn:com:appian:types:EXP}EXP_Receipt', null) /* comment */",
    '-1 + 2 * 3 ^ 2 & "x" <> "y"',
    "index(ri!a, 1, null),",
    "rule!x(_, 1)",
]


@pytest.mark.parametrize("source", SOURCES)
def test_parses_and_prints_back_identically(source: str) -> None:
    assert to_text(parse(source)) == normalise(source)


def test_syntax_errors_are_reported() -> None:
    with pytest.raises(SailSyntaxError):
        parse("if(ri!a, ")


def test_canonical_function_names_are_readable() -> None:
    call = parse('#"SYSTEM_SYSRULES_textField_v1"(label: "x")').root
    assert function_name(call.fn) == "a!textField"  # type: ignore[attr-defined]
    call = parse('#"urn:appian:function:v1:a:update"(data: 1)').root
    assert function_name(call.fn) == "a!update"  # type: ignore[attr-defined]


def _kinds(source: str) -> list[tuple[str, int]]:
    return [(b.kind, b.outcomes) for b in find(parse(source))]


def test_if_and_its_comparison_with_boundary_value() -> None:
    branches = find(parse("if(ri!amount > 50000, 1, 2)"))
    assert [(b.kind, b.outcomes) for b in branches] == [("if", 2), ("compare", 2)]
    assert branches[1].literals == ("50000",)


def test_match_choose_loops_and_null_checks() -> None:
    assert _kinds(
        'a!match(value: ri!x, equals: 1, then: "a", equals: 2, then: "b", '
        'default: "c", whenTrue: true, then: 1)'
    ) == [("match", 4)]
    assert _kinds("choose(ri!i, 1, 2, 3)") == [("choose", 3)]
    assert _kinds('#"SYSTEM_SYSRULES_forEach"(items: ri!l, expression: fv!item)') == [("loop", 3)]
    assert _kinds("a!isNullOrEmpty(ri!x)") == [("null_check", 2)]


def test_screen_conditions_only_when_not_constant() -> None:
    assert _kinds("a!textField(showWhen: ri!show, required: true)") == [("ui_condition", 2)]
