"""Print a SAIL tree back to text, and normalise source text, for the round-trip check.

Both sides drop whitespace and comments outside strings; everything else must match exactly.
"""

from __future__ import annotations

import re

from atg.sail.ast import (
    Arg,
    Args,
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
    Quoted,
    Str,
    Unary,
)

# Strings, quoted names and #"refs" are kept whole; comments and whitespace are dropped.
_TOKENS = re.compile(r'#"[^"]*"|"(?:[^"]|"")*"|\'[^\'\n]*\'|/\*[\s\S]*?\*/|\s+|[^\s"\'#/]+|.')


def normalise(source: str) -> str:
    out = []
    for m in _TOKENS.finditer(source.strip()):
        tok = m.group(0)
        if tok.isspace() or tok.startswith("/*"):
            continue
        out.append(tok)
    return "".join(out)


def to_text(expr: Expression) -> str:
    return (
        ("=" if expr.leading_equals else "") + _p(expr.root) + ("," if expr.trailing_comma else "")
    )


def print_node(n: Node) -> str:
    return _p(n)


def _args(args: Args) -> str:
    text = ",".join(_arg(a) for a in args.items)
    return text + ("," if args.trailing_comma else "")


def _arg(a: Arg) -> str:
    return (f"{a.key}:" if a.key is not None else "") + _p(a.value)


def _p(n: Node) -> str:
    match n:
        case Num(t) | Str(t) | Name(t) | Quoted(t):
            return t
        case Canon(t):
            return f'#"{t}"'
        case Call(fn, args):
            return f"{_p(fn)}({_args(args)})"
        case Index(target, args, dotted):
            return f"{_p(target)}{'.' if dotted else ''}[{_args(args)}]"
        case Dot(target, f):
            return f"{_p(target)}.{f}"
        case ListLit(args):
            return "{" + _args(args) + "}"
        case BinOp(op, left, right):
            return f"{_p(left)}{op}{_p(right)}"
        case Unary(op, operand):
            return f"{op}{_p(operand)}"
        case Paren(inner):
            return f"({_p(inner)})"
    raise TypeError(f"cannot print {type(n).__name__}")
