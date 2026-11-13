"""Walking a parsed SAIL tree: every node below one, a call's keyword argument, a function's
plain name (a!buttonWidget_v1 and #"SYSTEM_SYSRULES_ButtonWidgetSubmit" -> buttonwidget...)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from atg.sail.ast import Arg, BinOp, Call, Dot, Index, ListLit, Node, Paren, Unary
from atg.sail.branches import function_name


def plain_name(fn: Node) -> str:
    """a!buttonWidget_v1, #"SYSTEM_SYSRULES_ButtonWidgetSubmit", startProcess3 -> plain name."""
    name = function_name(fn).removeprefix("a!").lower()
    return re.sub(r"(_v\d+|\d+)$", "", name)


def keyword(call: Call, key: str) -> Node | None:
    return next((a.value for a in call.args.items if a.key == key), None)


def nodes(n: Node) -> Iterator[Node]:
    yield n
    match n:
        case Call(fn, args):
            yield from nodes(fn)
            yield from _args(args.items)
        case Index(target, args):
            yield from nodes(target)
            yield from _args(args.items)
        case ListLit(args):
            yield from _args(args.items)
        case Dot(target, _):
            yield from nodes(target)
        case BinOp(_, left, right):
            yield from nodes(left)
            yield from nodes(right)
        case Unary(_, operand) | Paren(operand):
            yield from nodes(operand)


def _args(items: tuple[Arg, ...]) -> Iterator[Node]:
    for a in items:
        yield from nodes(a.value)
