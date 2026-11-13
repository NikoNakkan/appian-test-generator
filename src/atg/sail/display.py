"""Show SAIL the way developers write it in Designer, keeping the original layout.

The export stores references in canonical form; this turns them back:
  #"SYSTEM_SYSRULES_textField_v1"            -> a!textField
  #"urn:appian:function:v1:a:update"          -> a!update
  #"_a-0000...", #"<uuid>"                    -> rule!Name, cons!Name, recordType!Name, ...
  #"urn:appian:record-field:v1:<rt>/<field>"  -> recordType!Rt.fields.field
  'type!{ns}Name'                              -> type!Name
  'recordType!{rt}Name.fields.{f}field'        -> recordType!Name.fields.field
Each replaced reference that names an object in the export carries that object's UUID, so the
viewer can link it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION = re.compile(r"_v\d+$")
_CANON = re.compile(r'#"([^"]*)"')
_QUOTED_TYPE = re.compile(r"'type!\{[^}]*\}([^']*)'")
_QUOTED_RECORD = re.compile(r"'recordType!\{([0-9a-fA-F-]{36})\}([^'.]*)((?:\.[^']*)?)'")
_FIELD_UUID = re.compile(r"\{([0-9a-fA-F-]{36})\}")
_DEBUG = "/*41707069616E-GEN-DEBUG*/"
_PREFIX = {
    "rule": "rule",
    "interface": "rule",
    "decision": "rule",
    "integration": "rule",
    "constant": "cons",
    "recordType": "recordType",
    "processModel": "processModel",
    "group": "group",
    "webApi": "webApi",
    "datatype": "type",
}

Segment = tuple[str, str | None]  # (text, uuid of the object it names, if any)
OUTSIDE = "outside"  # marks a reference to an object that is not in this export


@dataclass(frozen=True)
class Names:
    objects: dict[str, tuple[str, str]]  # uuid -> (type, name)
    fields: dict[str, str]  # record field uuid -> field name


def to_designer(source: str, names: Names) -> list[Segment]:
    text = source.replace(_DEBUG, "").strip()
    if text.startswith("=") and not text.startswith("=="):
        text = text[1:].lstrip()  # process expressions are saved with a leading "="
    out: list[Segment] = []
    pos = 0
    pattern = re.compile(f"{_CANON.pattern}|{_QUOTED_RECORD.pattern}|{_QUOTED_TYPE.pattern}")
    for m in pattern.finditer(text):
        out.append((text[pos : m.start()], None))
        out.append(_replace(m, names))
        pos = m.end()
    out.append((text[pos:], None))
    return _merge([s for s in out if s[0]])


def _replace(m: re.Match[str], names: Names) -> Segment:
    if m.group(1) is not None:
        return _canonical(m.group(1), names)
    if m.group(2) is not None:  # 'recordType!{rt}Name.fields.{f}field'
        rt, name, rest = m.group(2), m.group(3), m.group(4)
        rest = _FIELD_UUID.sub("", rest)
        return f"recordType!{names.objects.get(rt, ('', name))[1] or name}{rest}", rt
    return f"type!{m.group(5)}", None


def _canonical(inner: str, names: Names) -> Segment:
    if inner.startswith("SYSTEM_SYSRULES_"):
        return "a!" + _VERSION.sub("", inner.removeprefix("SYSTEM_SYSRULES_")), None
    if inner.startswith("urn:appian:function:v1:"):
        fn = inner.removeprefix("urn:appian:function:v1:").split("?")[0]
        return fn.replace("a:", "a!", 1) if fn.startswith("a:") else fn, None
    if inner.startswith("urn:appian:"):
        return _record_urn(inner, names)
    if inner in names.objects:
        kind, name = names.objects[inner]
        return f"{_PREFIX.get(kind, kind)}!{name}", inner
    if re.match(r"^(_[a-z]-)?[0-9a-fA-F]{8}-", inner):
        return f'#"{inner}"', OUTSIDE  # an object from another app: shown as-is, marked
    return f'#"{inner}"', None


def _record_urn(inner: str, names: Names) -> Segment:
    """urn:appian:record-field:v1:<rt>/<rel>/<field> -> recordType!Rt.<rel>.fields.<field>."""
    kind, _, rest = inner.removeprefix("urn:appian:").partition(":v1:")
    parts = rest.split("/")
    rt = parts[0]
    rt_name = names.objects.get(rt, ("", rt))[1]
    tail = [names.fields.get(p, names.objects.get(p, ("", p[:8]))[1]) for p in parts[1:]]
    if kind == "record-field" and tail:
        return f"recordType!{rt_name}" + "".join(
            f".{t}" for t in tail[:-1]
        ) + f".fields.{tail[-1]}", rt if rt in names.objects else None
    if kind == "record-relationship" and tail:
        return f"recordType!{rt_name}.relationships." + ".".join(tail), rt
    if kind == "user-filter" and tail:
        return f"recordType!{rt_name}.filters.{tail[-1]}", rt
    return f"recordType!{rt_name}", rt if rt in names.objects else None


def _merge(segments: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for text, link in segments:
        if out and link is None and out[-1][1] is None:
            out[-1] = (out[-1][0] + text, None)
        else:
            out.append((text, link))
    return out


def plain(segments: list[Segment]) -> str:
    return "".join(t for t, _ in segments)
