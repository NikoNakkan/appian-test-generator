"""SAIL shown as written in Designer, and the read-only Designer pages on a real export."""

from __future__ import annotations

import json
from pathlib import Path

from atg import store
from atg.layers.pipeline import run_layers
from atg.sail.display import OUTSIDE, Names, plain, to_designer
from atg.web import designer_api
from tests.conftest import demo_export, single_root
from tests.demo import spec

RULE = "_a-0000ebf2-65f4-8000-9cf4-011c48011c48_1"
CONS = "_a-0000ebf2-65f4-8000-9cf4-011c48011c48_2"
RT = "91b70937-07ac-4038-be6e-fe2336bc5559"
FIELD = "561f08bd-d537-4da3-863d-576c3396b558"
NAMES = Names(
    {RULE: ("rule", "GetDocs"), CONS: ("constant", "MAX"), RT: ("recordType", "Operations")},
    {FIELD: "status"},
)


def test_canonical_references_read_like_designer() -> None:
    source = (
        f'=/*41707069616E-GEN-DEBUG*/#"SYSTEM_SYSRULES_textField_v1"(label: #"{CONS}", '
        f'value: #"{RULE}"(id: ri!id)[#"urn:appian:record-field:v1:{RT}/{FIELD}"])'
    )
    assert plain(to_designer(source, NAMES)) == (
        "a!textField(label: cons!MAX, value: rule!GetDocs(id: ri!id)"
        "[recordType!Operations.fields.status])"
    )


def test_references_carry_links_and_outside_objects_are_marked() -> None:
    segments = to_designer(f'#"{RULE}"() & #"_a-0000aaaa-8303-8000-9d04-011c48011c48_9"()', NAMES)
    links = [link for _, link in segments if link]
    assert links == [RULE, OUTSIDE]


def test_quoted_types_functions_and_layout_are_kept() -> None:
    source = (
        "cast(\n  'type!{urn:com:appian:types:EXP}EXP_Receipt',\n"
        '  #"urn:appian:function:v1:a:update?okey=x"(data: 1)\n)'
    )
    assert plain(to_designer(source, NAMES)) == "cast(\n  type!EXP_Receipt,\n  a!update(data: 1)\n)"


def test_designer_pages_on_the_demo(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    sid, _ = run_layers(con, single_root(demo_export()))

    rule = designer_api.object_page(con, sid, spec.R_GET)
    assert "recordType!EXP_Claim.fields.id" in plain(rule["code"])
    assert [i["name"] for i in rule["details"]["inputs"]] == ["id"]

    constant = designer_api.object_page(con, sid, spec.C_LIMIT)
    assert constant["details"]["constant"] == {"type": "Integer", "values": ["500"]}

    sub = designer_api.node_page(con, sid, spec.PM_SUBMIT, 5)
    assert sub["calls"]["name"] == "EXP_Notify"
    pay = designer_api.node_page(con, sid, spec.PM_SUBMIT, 6)
    assert pay["outputs"][0]["target"] == "payment"
    assert "EXP_PayClaim" in plain(pay["inputs"][0]["segments"])
    gateway = designer_api.node_page(con, sid, spec.PM_SUBMIT, 1)
    assert {r["label"] for r in gateway["rules"]} == {"Yes", "default"}
    row = con.execute("SELECT details FROM object_details WHERE uuid = ?", (spec.PM_SUBMIT,))
    variables = json.loads(row.fetchone()[0])["variables"]
    assert [v["name"] for v in variables] == [
        "claim", "amount", "decision", "comment", "submitted", "payment"
    ]  # fmt: skip
