"""The demo export with what the agent tools need on top, written the way real apps do it:
a page gated through a constant that holds a group, a related action gated by a group named
directly, a grid of the user's own claims, role maps (who may start a process), a reminder
process on a timer, and a process started by a message that marks claims paid."""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.conftest import demo_export
from tests.demo import spec
from tests.demo.process import process
from tests.demo.xml import constant, content

C_GROUP = spec.cid(85)
PM_REMIND, PM_PAID = spec.uid(60), spec.uid(61)
OWN = f"{spec.fn('loggedInUser')}()"


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (path, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _roles(group: str) -> str:
    return (
        '<roleMap public="false"><role name="processModelInitiator"><users/>'
        f"<groups><groupUuid>{group}</groupUuid></groups></role></roleMap>"
    )


def _start(inputs: dict[str, str]) -> dict[str, object]:
    return {
        "gui": 0,
        "type": "core.0",
        "name": "Start Event",
        "label": "Start",
        "to": [1],
        "inputs": inputs,
    }


def _extra_processes(folder: Path) -> None:
    claim = ("claim", f"n1:{spec.RT}", 'xmlns:n1="urn:com:appian:recordtype:datatype"', True)
    status = spec.field(spec.RT, spec.F_STATUS)
    specs = [
        {
            "uuid": PM_REMIND,
            "name": "EXP_Reminder",
            "variables": [claim],
            "nodes": [
                _start({"timerExpression": "=today()"}),
                {
                    "gui": 1,
                    "type": "internal.38",
                    "name": "Sub-Process",
                    "label": "Remind",
                    "to": [2],
                    "calls": spec.PM_NOTIFY,
                },
                {"gui": 2, "type": "core.1", "name": "End Event", "label": "End"},
            ],
        },
        {
            "uuid": PM_PAID,
            "name": "EXP_MarkPaid",
            "variables": [claim],
            "nodes": [
                _start({"messageCorrelation": "=pv!claim"}),
                {
                    "gui": 1,
                    "type": "internal3.write_records_to_source_23r3",
                    "name": "Write Records",
                    "label": "Mark paid",
                    "to": [2],
                    "inputs": {"Records": f'=a!update(pv!claim, {status}, "Paid")'},
                },
                {"gui": 2, "type": "core.1", "name": "End Event", "label": "End"},
            ],
        },
    ]
    for pm in specs:
        uuid = str(pm["uuid"])
        text = process(pm, lambda g, u=uuid: spec.node_uuid(u, g))
        (folder / f"processModel/{uuid}.xml").write_text(text, encoding="utf-8")


def build(target: Path) -> Path:
    folder = target / "Expense Claims"
    shutil.copytree(demo_export(), folder)
    (folder / f"content/{C_GROUP}.xml").write_text(
        content("constant", "EXP_APPROVERS_GROUP", C_GROUP, constant("Group", spec.G_APPROVERS)),
        encoding="utf-8",
    )
    page_gate = f'a!isUserMemberOfGroup({OWN}, #"{C_GROUP}")'
    _replace_once(
        folder / f"site/{spec.SITE}.xml",
        "<urlStub>dashboard</urlStub>",
        f"<urlStub>dashboard</urlStub><visibilityExpr><![CDATA[{page_gate}]]></visibilityExpr>",
    )
    rt = folder / f"recordType/{spec.RT}.xml"
    text = rt.read_text(encoding="utf-8")
    at = text.index(f'a:uuid="{spec.ACT_WITHDRAW}"')
    end = text.index("<a:visibilityExpr/>", at)
    check = f'a!isUserMemberOfGroup(loggedInUser(), #"{spec.G_EMPLOYEES}")'
    rt.write_text(
        text[:end]
        + f"<a:visibilityExpr><![CDATA[{check}]]></a:visibilityExpr>"
        + text[end + len("<a:visibilityExpr/>") :],
        encoding="utf-8",
    )
    flt = f', filters: {spec.fn("queryFilter")}(field: "owner", operator: "=", value: {OWN})'
    data = f"recordType: {spec.record(spec.RT)}"
    _replace_once(folder / f"content/{spec.UI_LIST}.xml", f"{data})", f"{data}{flt})")
    for pm, group in ((spec.PM_SUBMIT, spec.G_EMPLOYEES), (spec.PM_WITHDRAW, spec.G_APPROVERS)):
        _replace_once(
            folder / f"processModel/{pm}.xml",
            "</processModelHaul>",
            _roles(group) + "</processModelHaul>",
        )
    _extra_processes(folder)
    return folder
