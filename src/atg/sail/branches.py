"""Decision points in a SAIL tree: everything a test has to drive both (or all) ways."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from atg.sail.ast import (
    Arg,
    BinOp,
    Call,
    Canon,
    Dot,
    Expression,
    Index,
    ListLit,
    Name,
    Node,
    Num,
    Paren,
    Str,
    Unary,
)
from atg.sail.printer import print_node

_VERSION = re.compile(r"_v\d+$")
_UUID = re.compile(r"^(_[a-z]-)?[0-9a-fA-F]{8}-")

NULL_CHECKS = {"a!isNullOrEmpty", "a!isNotNullOrEmpty", "isnull", "a!defaultValue"}
LOOPS = {"a!forEach", "apply", "reduce"}
UI_CONDITIONS = {"showWhen", "required", "disabled", "readOnly"}
LITERALS = (Num, Str)


@dataclass(frozen=True)
class Branch:
    kind: str  # if, match, choose, and, or, null_check, loop, ui_condition, compare
    function: str
    condition: str
    outcomes: int  # how many ways a test must drive it (if: 2, loop: 0/1/many = 3)
    literals: tuple[str, ...] = field(default=())  # values compared against: test boundaries


def function_name(fn: Node) -> str:
    """Readable name of a called function: a!forEach, if, or rule:<uuid> for app rules."""
    if isinstance(fn, Name):
        return fn.text
    if isinstance(fn, Canon):
        t = fn.text
        if t.startswith("SYSTEM_SYSRULES_"):
            return "a!" + _VERSION.sub("", t.removeprefix("SYSTEM_SYSRULES_"))
        if t.startswith("urn:appian:function:v1:"):
            return t.removeprefix("urn:appian:function:v1:").split("?")[0].replace("a:", "a!", 1)
        if _UUID.match(t):
            return "rule:" + t
        return t
    return "?"


def find(expr: Expression) -> list[Branch]:
    return list(_walk(expr.root))


def _walk(n: Node) -> Iterator[Branch]:
    match n:
        case Call(fn, args):
            yield from _call(function_name(fn), args.items)
            yield from _walk(fn)
            for a in args.items:
                yield from _walk(a.value)
        case Index(target, args):
            yield from _walk(target)
            for a in args.items:
                yield from _walk(a.value)
        case Dot(target, _):
            yield from _walk(target)
        case ListLit(args):
            for a in args.items:
                yield from _walk(a.value)
        case BinOp(op, left, right):
            if op in {"=", "<>", "<", ">", "<=", ">="}:
                lits = tuple(print_node(x) for x in (left, right) if isinstance(x, LITERALS))
                yield Branch("compare", op, _text(n), 2, lits)
            yield from _walk(left)
            yield from _walk(right)
        case Unary(_, operand) | Paren(operand):
            yield from _walk(operand)


def _call(fname: str, args: tuple[Arg, ...]) -> Iterator[Branch]:
    positional = [a.value for a in args if a.key is None]
    if fname == "if" and positional:
        yield Branch("if", fname, _text(positional[0]), 2)
    elif fname == "a!match":
        cases = sum(a.key in {"equals", "whenTrue"} for a in args)  # each case, plus default
        yield Branch("match", fname, _text(_kw(args, "value") or positional[0]), cases + 1)
    elif fname == "choose" and positional:
        yield Branch("choose", fname, _text(positional[0]), max(1, len(positional) - 1))
    elif fname in {"and", "or"}:
        yield Branch(fname, fname, ", ".join(_text(p) for p in positional), 2)
    elif fname in NULL_CHECKS and positional:
        yield Branch("null_check", fname, _text(positional[0]), 2)
    elif fname in LOOPS:
        items = _kw(args, "items") or (positional[0] if positional else None)
        yield Branch("loop", fname, _text(items) if items else "", 3)
    for a in args:
        if a.key in UI_CONDITIONS and not _is_constant(a.value):
            yield Branch("ui_condition", a.key, _text(a.value), 2)


def _kw(args: tuple[Arg, ...], key: str) -> Node | None:
    return next((a.value for a in args if a.key == key), None)


def _is_constant(n: Node) -> bool:
    return (
        isinstance(n, LITERALS)
        or (isinstance(n, Name) and n.text in {"true", "false", "null"})
        or (isinstance(n, Call) and function_name(n.fn) in {"true", "false"} and not n.args.items)
    )


def _text(n: Node) -> str:
    text = print_node(n)
    return text if len(text) <= 300 else text[:297] + "..."
