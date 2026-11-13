"""Readable condition phrases, and splitting node outputs at the right colon."""

from __future__ import annotations

import pytest

from atg.sail.display import Names
from atg.sail.explain import phrase, split_output

N = Names(objects={}, fields={})


@pytest.mark.parametrize(
    ("source", "negate", "expected"),
    [
        ("=if(a!isNullOrEmpty(pv!doc), false, true)", False, "doc is filled in"),
        ("=if(a!isNullOrEmpty(pv!doc), false, true)", True, "doc is empty"),
        ("=pv!submitted", False, "submitted is true"),
        ("=pv!submitted", True, "submitted is false"),
        ("=not(pv!ok)", False, "ok is false"),
        ('=or(pv!a = "x", pv!a = "y")', True, 'a ≠ "x", and a ≠ "y"'),
        ("=and(pv!n > 1, pv!m <= 2)", False, "n > 1, and m ≤ 2"),
        ("=and(pv!n > 1, pv!m <= 2)", True, "n ≤ 1, or m > 2"),
        ("=true()", False, "always"),
        ("=true()", True, "never"),
        ("=a!isNotNullOrEmpty(ri!x)", False, "x is filled in"),
        ("", False, ""),
    ],
)
def test_phrase(source: str, negate: bool, expected: str) -> None:
    assert phrase(source, N, negate) == expected


def test_unparseable_falls_back_to_text() -> None:
    assert phrase("=pv!a ((", N).endswith("is true")


def test_split_output_skips_colons_inside_brackets_and_quotes() -> None:
    assert split_output('op[#"urn:appian:x:y"]: pv!z') == ('op[#"urn:appian:x:y"]', "pv!z")
    assert split_output("a: b: c") == ("a", "b: c")
    assert split_output("no colon") == ("no colon", "")
