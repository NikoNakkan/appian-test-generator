"""SAIL syntax tree and parser. Nodes print back (printer.py) for the round-trip check."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from lark import Lark, Token, Transformer
from lark.exceptions import LarkError


class Node:
    """Base class for every SAIL syntax node."""


@dataclass(frozen=True)
class Num(Node):
    text: str


@dataclass(frozen=True)
class Str(Node):
    text: str  # with its quotes and "" escapes, exactly as written


@dataclass(frozen=True)
class Name(Node):
    text: str  # local!x, ri!x, a!forEach, if, true, _


@dataclass(frozen=True)
class Canon(Node):
    text: str  # inside of #"...": a UUID, SYSTEM_SYSRULES_x or an urn


@dataclass(frozen=True)
class Quoted(Node):
    text: str  # with its quotes: 'type!{ns}Name'


@dataclass(frozen=True)
class Arg(Node):
    value: Node
    key: str | None = None  # "label" for label: value


@dataclass(frozen=True)
class Args:
    items: tuple[Arg, ...] = ()
    trailing_comma: bool = False


@dataclass(frozen=True)
class Call(Node):
    fn: Node
    args: Args = Args()


@dataclass(frozen=True)
class Index(Node):
    target: Node
    args: Args = Args()
    dotted: bool = False  # record field access written x.[#"urn:..."]


@dataclass(frozen=True)
class Dot(Node):
    target: Node
    field: str


@dataclass(frozen=True)
class ListLit(Node):
    args: Args = Args()  # keyed items make it a dictionary


@dataclass(frozen=True)
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Unary(Node):
    op: str
    operand: Node


@dataclass(frozen=True)
class Paren(Node):
    inner: Node


@dataclass(frozen=True)
class Expression:
    """A parsed SAIL source. Process expressions start with '=', kept for printing."""

    root: Node
    leading_equals: bool = False
    trailing_comma: bool = False  # some saved rules end in a stray "," that Appian accepts
    size: int = field(default=0, compare=False)


class SailSyntaxError(Exception):
    pass


class _ToAst(Transformer[Token, Node]):
    def num(self, c: list[Token]) -> Node:
        return Num(str(c[0]))

    def string(self, c: list[Token]) -> Node:
        return Str(str(c[0]))

    def canon(self, c: list[Token]) -> Node:
        return Canon(str(c[0])[2:-1])

    def quoted(self, c: list[Token]) -> Node:
        return Quoted(str(c[0]))

    def name(self, c: list[Token]) -> Node:
        return Name(str(c[0]))

    def args(self, c: list[object]) -> Args:
        trailing = bool(c) and c[-1] is _TRAILING
        items = c[:-1] if trailing else c
        return Args(tuple(a if isinstance(a, Arg) else Arg(_node(a)) for a in items), trailing)

    def trailing(self, c: list[object]) -> object:
        return _TRAILING

    def kwarg(self, c: list[object]) -> Arg:
        key = str(c[0]).rstrip()[:-1].rstrip()
        value = c[1]
        assert isinstance(value, Node)
        return Arg(value, key)

    def field(self, c: list[Token]) -> str:
        return str(c[0])

    def call(self, c: list[object]) -> Node:
        return Call(_node(c[0]), _args(c[1:]))

    def index(self, c: list[object]) -> Node:
        return Index(_node(c[0]), _args(c[1:]))

    def dot_index(self, c: list[object]) -> Node:
        return Index(_node(c[0]), _args(c[1:]), dotted=True)

    def dot(self, c: list[object]) -> Node:
        return Dot(_node(c[0]), str(c[1]))

    def list_literal(self, c: list[object]) -> Node:
        return ListLit(_args(c))

    def paren(self, c: list[object]) -> Node:
        return Paren(_node(c[0]))

    def compare(self, c: list[object]) -> Node:
        return BinOp(str(c[1]), _node(c[0]), _node(c[2]))

    def arith(self, c: list[object]) -> Node:
        return BinOp(str(c[1]), _node(c[0]), _node(c[2]))

    def concat(self, c: list[object]) -> Node:
        return BinOp("&", _node(c[0]), _node(c[1]))

    def power(self, c: list[object]) -> Node:
        return BinOp("^", _node(c[0]), _node(c[1]))

    def unary(self, c: list[object]) -> Node:
        return Unary(str(c[0]), _node(c[1]))


def _node(x: object) -> Node:
    assert isinstance(x, Node), x
    return x


_TRAILING = object()


def _args(rest: list[object]) -> Args:
    if not rest:
        return Args()
    assert isinstance(rest[0], Args)
    return rest[0]


@cache
def _parser() -> Lark:
    grammar = (Path(__file__).parent / "grammar.lark").read_text(encoding="utf-8")
    return Lark(grammar, parser="lalr", lexer="contextual", propagate_positions=False)


def parse(source: str) -> Expression:
    text = source.strip()
    leading = text.startswith("=")
    if leading:
        text = text[1:]
    trailing = text.endswith(",")
    if trailing:
        text = text[:-1]
    try:
        tree = _parser().parse(text)
    except LarkError as e:
        raise SailSyntaxError(str(e).splitlines()[0][:300]) from None
    root = _ToAst().transform(tree)
    return Expression(_node(root), leading, trailing, len(source))
