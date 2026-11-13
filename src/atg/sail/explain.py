"""Turn a SAIL condition into a short readable phrase, or the phrase for it being false.

  if(a!isNullOrEmpty(pv!doc), false, true)  -> "doc is filled in"
  pv!sent                                   -> "sent is true"  (negated: "sent is false")
  or(a, b)                                  -> "a, or b"  (negated: "not a, and not b")
  pv!op[#"urn:...record-field:...status"]=1 -> "op.status = 1"
Anything the patterns don't cover falls back to the Designer-form text plus "is true/false".
"""

from __future__ import annotations

import re

from atg.sail.ast import BinOp, Call, Name, Node, Num, Paren, SailSyntaxError, Str, parse
from atg.sail.branches import function_name
from atg.sail.display import Names, plain, to_designer
from atg.sail.printer import print_node

_EMPTY = {"a!isNullOrEmpty", "isnull"}
_FILLED = {"a!isNotNullOrEmpty"}
_FLIP = {"=": "≠", "<>": "=", ">": "≤", "<": "≥", ">=": "<", "<=": ">"}
_SHOW = {"=": "=", "<>": "≠", ">": ">", "<": "<", ">=": "≥", "<=": "≤"}
_FIELD_INDEX = re.compile(r"\[recordType!\w+\.fields\.(\w+)\]")
_FIELD = re.compile(r"recordType!(\w+)\.fields\.(\w+)")
_PREFIX = re.compile(r"\b(?:pv|ri|local)!")
_MAX = 90


def phrase(source: str, names: Names, negate: bool = False) -> str:
    if not source.strip():
        return ""
    try:
        root = parse(source).root
    except SailSyntaxError:
        text = _tidy(plain(to_designer(source, names)))
        return f"{text} is {'false' if negate else 'true'}"
    return _say(root, negate, names)


def _say(n: Node, neg: bool, names: Names) -> str:
    if isinstance(n, Paren):
        return _say(n.inner, neg, names)
    if isinstance(n, Call):
        fn = function_name(n.fn)
        args = [a.value for a in n.args.items if a.key is None]
        if (
            fn == "if"
            and len(args) == 3
            and _bool(args[1]) is not None
            and _bool(args[2]) is not None
        ):
            same = _bool(args[1]) and not _bool(args[2])
            return _say(args[0], neg if same else not neg, names)
        if fn in _EMPTY | _FILLED and args:
            empty = (fn in _EMPTY) != neg
            return f"{_operand(args[0], names)} is {'empty' if empty else 'filled in'}"
        if fn == "not" and args:
            return _say(args[0], not neg, names)
        if fn in {"and", "or"} and args:
            joiner = "and" if (fn == "and") != neg else "or"
            return f", {joiner} ".join(_say(a, neg, names) for a in args)
        if fn in {"true", "false"} and not args:
            return "always" if (fn == "true") != neg else "never"
    if isinstance(n, BinOp) and n.op in _SHOW:
        op = _FLIP[n.op] if neg else _SHOW[n.op]
        return f"{_operand(n.left, names)} {op} {_operand(n.right, names)}"
    if isinstance(n, Name) and n.text in {"true", "false"}:
        return "always" if (n.text == "true") != neg else "never"
    return f"{_operand(n, names)} is {'false' if neg else 'true'}"


def split_output(text: str) -> tuple[str, str]:
    """`target: expression` from a node output. The target may hold colons itself, inside
    brackets or quotes (claim[#"urn:appian:..."]: value), so split at the first colon
    outside them."""
    depth, quote = 0, False
    for i, ch in enumerate(text):
        if ch == '"':
            quote = not quote
        elif not quote and ch in "[(":
            depth += 1
        elif not quote and ch in "])":
            depth -= 1
        elif not quote and depth == 0 and ch == ":":
            return text[:i].strip(), text[i + 1 :].strip()
    return text.strip(), ""


def target_name(target: str, names: Names) -> str:
    """A readable output target: claim[#"urn:...status"] -> claim.status."""
    return _tidy(plain(to_designer(target, names)))


def _bool(n: Node) -> bool | None:
    if isinstance(n, Name) and n.text in {"true", "false"}:
        return n.text == "true"
    if isinstance(n, Call) and function_name(n.fn) in {"true", "false"} and not n.args.items:
        return function_name(n.fn) == "true"
    return None


def _operand(n: Node, names: Names) -> str:
    if isinstance(n, Num | Str):
        return print_node(n)
    return _tidy(plain(to_designer(print_node(n), names)))


def _tidy(text: str) -> str:
    """Shorter names: pv!op[recordType!Op.fields.status] -> op.status, rule!X -> X."""
    text = _FIELD_INDEX.sub(r".\1", text)
    text = _FIELD.sub(r"\1.\2", text)
    text = _PREFIX.sub("", text).replace("rule!", "")
    text = re.sub(
        r"(?<=\w):(?=\S)", ": ", re.sub(r",(?=\S)", ", ", text)
    )  # (a:1,b:2) -> (a: 1, b: 2)
    text = " ".join(text.split())
    return text if len(text) <= _MAX else text[: _MAX - 1] + "…"
