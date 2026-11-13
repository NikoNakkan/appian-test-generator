"""The Expense Claims app: every object, its SAIL and its process flow. Names are made up."""

from __future__ import annotations

from typing import Any

from tests.demo.process import form


def uid(n: int) -> str:
    return f"d3e0{n:04x}-0000-4000-8000-{n:012x}"


def cid(n: int) -> str:
    """Content objects (rules, interfaces, constants) use Appian's _a-..._n form."""
    return f"_a-0000d3e0-0000-8000-9000-000000000000_{n}"


def node_uuid(pm: str, gui: int) -> str:
    return f"{pm[:4]}{gui:04x}-0000-4000-8000-{int(pm[-4:], 16):08x}{gui:04x}"


APP, G_EMPLOYEES, G_APPROVERS = uid(1), uid(2), uid(3)
RT, F_ID, F_TITLE, F_AMOUNT, F_STATUS, F_TOTAL = (
    uid(10),
    uid(11),
    uid(12),
    uid(13),
    uid(14),
    uid(15),
)
REL_LINES, ACT_NEW, ACT_WITHDRAW = uid(16), uid(17), uid(18)
RT_LINE, L_ID, L_CLAIM, L_DESC, L_AMOUNT, REL_CLAIM = (
    uid(20),
    uid(21),
    uid(22),
    uid(23),
    uid(24),
    uid(25),
)
CS, INT_PAY = cid(30), cid(31)
SITE, PAGE_CLAIMS, PAGE_TASKS = uid(40), uid(41), uid(42)
PM_SUBMIT, PM_NOTIFY, PM_WITHDRAW, WEB_API, PAGE_DASH = uid(50), uid(51), uid(52), uid(55), uid(43)
UI_LIST, UI_SUMMARY, UI_CLAIM, UI_LINES, UI_REVIEW, UI_UNUSED, UI_DASH = (
    cid(n) for n in range(60, 67)
)
R_NEEDS, R_TOTAL, R_GET, C_LIMIT = cid(70), cid(71), cid(72), cid(80)
# In another app: referenced, never exported.
OUTSIDE_RULE, OUTSIDE_PM, OUTSIDE_TASKS = cid(99), uid(98), uid(97)

T = "http://www.appian.com/ae/types/2009"
RT_NS = "urn:com:appian:recordtype:datatype"


def field(rt: str, f: str) -> str:
    return f'#"urn:appian:record-field:v1:{rt}/{f}"'


def record(rt: str) -> str:
    return f'#"urn:appian:record-type:v1:{rt}"'


def fn(name: str) -> str:
    """A built-in a!name as Appian stores it."""
    return f'#"SYSTEM_SYSRULES_{name}"'


SIMPLE = [
    (
        "applicationHaul",
        "application",
        "Expense Claims",
        APP,
        "    <description>Employees claim expenses; approvers review them.</description>\n",
    ),
    ("groupHaul", "group", "EXP_Employees", G_EMPLOYEES, ""),
    ("groupHaul", "group", "EXP_Approvers", G_APPROVERS, ""),
    ("connectedSystemHaul", "connectedSystem", "EXP_PaymentsAPI", CS, ""),
]
PAGES = [
    (PAGE_CLAIMS, "Claims", "claims", UI_LIST, "ContentFreeformRule"),
    (PAGE_DASH, "Dashboard", "dashboard", UI_DASH, "ContentFreeformRule"),
    (PAGE_TASKS, "My tasks", "tasks", OUTSIDE_TASKS, "TaskReport"),
]
RECORD_TYPES: list[dict[str, Any]] = [
    {
        "uuid": RT, "name": "EXP_Claim", "stub": "claims", "table": "exp_claim",
        "fields": [(F_ID, "id", "Integer", "id", ""), (F_TITLE, "title", "Text", "title", ""),
                   (F_AMOUNT, "amount", "Decimal", "amount", ""), (F_STATUS, "status", "Text", "status", ""),
                   (F_TOTAL, "amountWithTax", "Decimal", "", f"rv!record[{field(RT, F_AMOUNT)}] * 1.2")],
        "relationships": [(REL_LINES, "lines", RT_LINE, "ONE_TO_MANY")],
        "actions": [("recordListActionCfg", "staticTitle", ACT_NEW, "New claim", PM_SUBMIT),
                    ("relatedActionCfg", "staticTitleString", ACT_WITHDRAW, "Withdraw", PM_WITHDRAW)],
        "view": f'#"{UI_SUMMARY}"(record: rv!record)',
    },
    {
        "uuid": RT_LINE, "name": "EXP_ClaimLine", "stub": "claim-lines", "table": "exp_claim_line",
        "fields": [(L_ID, "id", "Integer", "id", ""), (L_CLAIM, "claimId", "Integer", "claim_id", ""),
                   (L_DESC, "description", "Text", "description", ""), (L_AMOUNT, "amount", "Decimal", "amount", "")],
        "relationships": [(REL_CLAIM, "claim", RT, "MANY_TO_ONE")],
        "actions": [],
    },
]  # fmt: skip


def processes() -> list[dict[str, Any]]:
    claim = ("claim", f"n1:{RT}", 'xmlns:n1="urn:com:appian:recordtype:datatype"', True)
    review = f'#"{UI_REVIEW}"(claim: ac!claim, decision: ac!decision, comment: ac!comment, submitted: ac!submitted)'
    return [
        {"uuid": PM_SUBMIT, "name": "EXP_SubmitClaim", "desc": "An employee submits a claim; big ones are reviewed.",
         "variables": [claim, ("amount", "xsd:double", "", True), ("decision", "xsd:string", "", False),
                       ("comment", "xsd:string", "", False), ("submitted", "xsd:boolean", "", False),
                       ("payment", "n2:EXP_Payment", 'xmlns:n2="urn:com:appian:types:EXP"', False)],
         "start_form": form(UI_CLAIM, f'#"{UI_CLAIM}"(claim: pv!claim, amount: pv!amount)'),
         "nodes": [
             {"gui": 0, "type": "core.0", "name": "Start Event", "label": "Start", "to": [1]},
             {"gui": 1, "type": "core.4", "name": "XOR", "label": "Needs approval?", "to": [2, 4],
              "rules": [(f'=#"{R_NEEDS}"(amount: pv!amount)', 2, "Yes")], "default": 4},
             {"gui": 2, "type": "internal.17", "name": "User Input Task", "label": "Review claim", "to": [3],
              "group": G_APPROVERS, "form": form(UI_REVIEW, review), "outputs": ["decision: ac!decision", "comment: ac!comment", "submitted: ac!submitted"]},
             {"gui": 3, "type": "core.4", "name": "XOR", "label": "Approved?", "to": [4, 5],
              "rules": [('=pv!decision = "Approve"', 4, "Approved")], "default": 5},
             {"gui": 4, "type": "internal3.write_records_to_source_23r3", "name": "Write Records", "label": "Save claim", "to": [6],
              "inputs": {"Records": f'=a!update(pv!claim, {field(RT, F_STATUS)}, "Approved")'}},
             {"gui": 5, "type": "internal.38", "name": "Sub-Process", "label": "Tell employee", "to": [7], "calls": PM_NOTIFY},
             {"gui": 6, "type": "internal3.integration", "name": "Call Integration", "label": "Pay claim", "to": [7],
              "inputs": {"Integration": f'=#"{INT_PAY}"(claimId: pv!claim)'}, "outputs": ["payment: ac!result"]},
             {"gui": 7, "type": "core.1", "name": "End Event", "label": "End"},
         ]},
        {"uuid": PM_NOTIFY, "name": "EXP_Notify", "variables": [("message", "xsd:string", "", True)],
         "nodes": [
             {"gui": 0, "type": "core.0", "name": "Start Event", "label": "Start", "to": [1]},
             {"gui": 1, "type": "internal.16", "name": "Script Task", "label": "Build message", "to": [2],
              "outputs": ['message: "Your claim was not approved"']},
             {"gui": 2, "type": "core.1", "name": "End Event", "label": "End"},
         ]},
        {"uuid": PM_WITHDRAW, "name": "EXP_Withdraw", "variables": [claim],
         "nodes": [
             {"gui": 0, "type": "core.0", "name": "Start Event", "label": "Start", "to": [1]},
             {"gui": 1, "type": "internal3.write_records_to_source_23r3", "name": "Write Records", "label": "Mark withdrawn", "to": [2],
              "inputs": {"Records": f'=a!update(pv!claim, {field(RT, F_STATUS)}, "Withdrawn")'}},
             {"gui": 2, "type": "core.1", "name": "End Event", "label": "End"},
         ]},
    ]  # fmt: skip
