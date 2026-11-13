"""Unit tests on tiny hand-written XML: how each kind of token is classified."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from atg.model import RefKind, UuidUse
from atg.read.scan import scan

SELF = "_a-0000ec54-8303-8000-9d04-011c48011c48_1"
OTHER = "_a-0000ec54-8303-8000-9d04-011c48011c48_2"
RT = "91b70937-07ac-4038-be6e-fe2336bc5559"
FIELD = "561f08bd-d537-4da3-9e8e-111111111111"
VERSION = "_a-0000ec54-8303-8000-9d04-011c48011c48_9"


def _scan(definition: str) -> tuple[set[tuple[RefKind, str]], list[tuple[str, UuidUse]], int]:
    xml = (
        f"<contentHaul><versionUuid>{VERSION}</versionUuid><rule><uuid>{SELF}</uuid>"
        f"<definition><![CDATA[{definition}]]></definition></rule></contentHaul>"
    )
    s = scan(ET.fromstring(xml), SELF)
    refs = {(r.kind, r.target) for r in s.references}
    return refs, [(t.token, t.use) for t in s.tokens], len(s.pending)


def test_rule_call_by_uuid_is_a_sail_reference() -> None:
    refs, tokens, pending = _scan(f'#"{OTHER}"(x: 1)')
    assert (RefKind.SAIL, OTHER) in refs
    assert (OTHER, UuidUse.REFERENCE) in tokens
    assert pending == 0


def test_platform_functions_are_not_references_to_objects() -> None:
    platform = '#"SYSTEM_SYSRULES_textField"(label: "a") & #"urn:appian:function:v1:a:update"'
    refs, _, _ = _scan(platform)
    assert {k for k, _ in refs} == {RefKind.PLATFORM}


def test_record_field_urn_points_at_the_record_type() -> None:
    refs, tokens, _ = _scan(f'local!x[#"urn:appian:record-field:v1:{RT}/{FIELD}"]')
    assert (RefKind.RECORD_TYPE, RT) in refs
    assert (FIELD, UuidUse.URN_PART) in tokens


def test_version_and_self_are_never_references() -> None:
    _, tokens, _ = _scan("1 + 1")
    assert (VERSION, UuidUse.VERSION) in tokens
    assert (SELF, UuidUse.SELF) in tokens


def test_custom_type_reference() -> None:
    refs, _, _ = _scan("cast('type!{urn:com:appian:types:EXP}EXP_Receipt', null)")
    assert (RefKind.TYPE, "{urn:com:appian:types:EXP}EXP_Receipt") in refs


def test_platform_type_is_ignored() -> None:
    refs, _, _ = _scan("'type!{http://www.appian.com/ae/types/2009}Dictionary'")
    assert not refs


def test_record_type_using_its_own_fields_is_self_not_a_reference() -> None:
    xml = (
        f'<recordTypeHaul><recordType a:uuid="{RT}" xmlns:a="x" name="R"><a:expr>'
        f'#"urn:appian:record-field:v1:{RT}/{FIELD}"</a:expr></recordType></recordTypeHaul>'
    )
    s = scan(ET.fromstring(xml), RT)
    assert {r.kind for r in s.references} == {RefKind.SELF}
    assert (RT, UuidUse.SELF) in [(t.token, t.use) for t in s.tokens]
