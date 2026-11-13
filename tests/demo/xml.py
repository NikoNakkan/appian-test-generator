"""XML for each kind of Appian object, in the shape real exports use (20+ "Haul" files).

Only the elements the reader looks at are written. SAIL goes in CDATA, exactly as Appian
stores it: own objects as #"<uuid>", built-ins as #"SYSTEM_SYSRULES_x", record fields as urns.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

A = 'xmlns:a="http://www.appian.com/ae/types/2009"'
XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'


def cdata(text: str) -> str:
    return f"<![CDATA[{text}]]>"


def content(kind: str, name: str, uuid: str, body: str, *, desc: str = "", tests: str = "") -> str:
    """A contentHaul: rule, interface, constant or outboundIntegration."""
    return (
        f"{HEAD}<contentHaul {A}>\n  <{kind}>\n    <name>{name}</name>\n    <uuid>{uuid}</uuid>\n"
        f"    <description>{escape(desc)}</description>\n{body}  </{kind}>\n{tests}</contentHaul>\n"
    )


def definition(sail: str) -> str:
    return f"    <definition>{cdata(sail)}</definition>\n"


def inputs(*pairs: tuple[str, str, str]) -> str:
    """Rule inputs as (name, type name, namespace)."""
    return "".join(
        f"    <namedTypedValue><name>{n}</name><type><name>{t}</name>"
        f"<namespace>{ns}</namespace></type></namedTypedValue>\n"
        for n, t, ns in pairs
    )


def saved_tests(*tests: tuple[str, dict[str, str]]) -> str:
    """Test inputs saved in Designer: (test name, {input: SAIL value})."""
    cases = "".join(
        f"      <el><a:name>{name}</a:name>"
        + "".join(
            f'<a:ruleInputTestConfigs><a:value {XSI} xsi:type="a:Expression">{cdata(v)}</a:value>'
            f"<a:nameRef>{k}</a:nameRef></a:ruleInputTestConfigs>"
            for k, v in values.items()
        )
        + f'<a:assertions {XSI} xsi:nil="true"/></el>\n'
        for name, values in tests
    )
    return (
        "  <typedValue><type><name>RuleTestConfig?list</name>"
        "<namespace>http://www.appian.com/ae/types/2009</namespace></type>\n"
        f"    <value>\n{cases}    </value>\n  </typedValue>\n"
    )


def constant(type_name: str, value: str) -> str:
    return (
        "    <typedValue><type>"
        f"<name>{type_name}</name><namespace>http://www.appian.com/ae/types/2009</namespace>"
        f"</type><value>{value}</value></typedValue>\n"
    )


def simple(haul: str, kind: str, name: str, uuid: str, extra: str = "") -> str:
    """application, group or connectedSystem: a name, a uuid and a few settings."""
    return (
        f"{HEAD}<{haul} {A}>\n  <{kind}>\n    <name>{name}</name>\n    <uuid>{uuid}</uuid>\n"
        f"{extra}  </{kind}>\n</{haul}>\n"
    )


def record_type(spec: dict[str, object]) -> str:
    fields = "".join(
        f"      <field><uuid>{u}</uuid><type>{{http://www.appian.com/ae/types/2009}}{t}</type>"
        f"<sourceFieldName>{col}</sourceFieldName><fieldName>{n}</fieldName>"
        f"<isRecordId>{'true' if n == 'id' else 'false'}</isRecordId>"
        + (
            f"<isCustomField>true</isCustomField><customFieldExpr>{cdata(expr)}</customFieldExpr>"
            if expr
            else "<isCustomField>false</isCustomField>"
        )
        + "</field>\n"
        for u, n, t, col, expr in spec["fields"]  # type: ignore[attr-defined]
    )
    rels = "".join(
        f"    <a:recordRelationshipCfg><uuid>{u}</uuid><relationshipName>{n}</relationshipName>"
        f"<targetRecordTypeUuid>{target}</targetRecordTypeUuid>"
        f"<relationshipType>{kind}</relationshipType></a:recordRelationshipCfg>\n"
        for u, n, target, kind in spec["relationships"]  # type: ignore[attr-defined]
    )
    actions = "".join(
        f'    <a:{tag} a:uuid="{u}"><a:{title_tag}>{title}</a:{title_tag}>'
        f'<a:target a:uuid="{pm}" xsi:type="a:ProcessModel"/><a:visibilityExpr/></a:{tag}>\n'
        for tag, title_tag, u, title, pm in spec["actions"]  # type: ignore[attr-defined]
    )
    view = spec.get("view")
    views = (
        f"    <a:detailViewCfg><a:nameExpr>{cdata('Summary')}</a:nameExpr>"
        f"<a:uiExpr>{cdata(str(view))}</a:uiExpr><a:urlStub>summary</a:urlStub></a:detailViewCfg>\n"
        if view
        else ""
    )
    return (
        f'{HEAD}<recordTypeHaul {A} {XSI}>\n  <recordType a:uuid="{spec["uuid"]}" name="{spec["name"]}">\n'
        f"    <a:urlStub>{spec['stub']}</a:urlStub>\n{views}{actions}{rels}"
        f"    <a:sourceConfiguration><sourceUuid>{spec['table']}@jdbc/Demo</sourceUuid>"
        f"<sourceType>RDBMS_TABLE</sourceType><friendlyName>{spec['table']}</friendlyName>\n{fields}"
        "      <refreshSchedule><frequency>DAILY</frequency>"
        '<value>{"hour":2,"minute":"00","amPM":"AM"}</value><activated>true</activated>'
        "</refreshSchedule>\n    </a:sourceConfiguration>\n  </recordType>\n</recordTypeHaul>\n"
    )


def site(uuid: str, name: str, stub: str, pages: list[tuple[str, str, str, str, str]]) -> str:
    """pages: (page uuid, title, url stub, target uuid, target xsi type)."""
    body = "".join(
        f'    <page a:uuid="{pu}"><staticName>{title}</staticName><urlStub>{ps}</urlStub>'
        f'<uiObject a:uuid="{target}" xsi:type="a:{kind}"/></page>\n'
        for pu, title, ps, target, kind in pages
    )
    return (
        f'{HEAD}<siteHaul {A} {XSI}>\n  <site a:uuid="{uuid}" name="{name}">\n'
        f"    <urlStub>{stub}</urlStub>\n{body}  </site>\n</siteHaul>\n"
    )


def datatype(namespace: str, name: str, fields: list[tuple[str, str]]) -> str:
    elements = "".join(
        f'      <xsd:element name="{n}" nillable="true" type="xsd:{t}"/>\n' for n, t in fields
    )
    return (
        f'{HEAD}<xsd:schema targetNamespace="{namespace}" xmlns:tns="{namespace}" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        f'  <xsd:complexType name="{name}">\n    <xsd:sequence>\n{elements}'
        "    </xsd:sequence>\n  </xsd:complexType>\n</xsd:schema>\n"
    )


def web_api(uuid: str, name: str, alias: str, method: str, sail: str) -> str:
    return (
        f'{HEAD}<webApiHaul {A}>\n  <webApi a:uuid="{uuid}" name="{name}">\n'
        f"    <a:urlAlias>{alias}</a:urlAlias>\n    <a:httpMethod>{method}</a:httpMethod>\n"
        f"    <a:expression>{cdata(sail)}</a:expression>\n  </webApi>\n</webApiHaul>\n"
    )
