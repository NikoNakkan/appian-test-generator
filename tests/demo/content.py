"""SAIL and XML of the demo's rules, screens, constant and integration (see spec.py for the rest)."""

from __future__ import annotations

from tests.demo.spec import (
    ACT_NEW,
    C_LIMIT,
    CS,
    F_AMOUNT,
    F_ID,
    F_STATUS,
    F_TITLE,
    INT_PAY,
    L_AMOUNT,
    L_DESC,
    OUTSIDE_PM,
    OUTSIDE_RULE,
    R_GET,
    R_NEEDS,
    R_TOTAL,
    REL_LINES,
    RT,
    RT_LINE,
    RT_NS,
    UI_CLAIM,
    UI_DASH,
    UI_LINES,
    UI_LIST,
    UI_REVIEW,
    UI_SUMMARY,
    UI_UNUSED,
    T,
    field,
    fn,
    record,
)
from tests.demo.xml import constant, content, definition, inputs, saved_tests

API_SAIL = f'{fn("httpResponse_v1")}(statusCode: 200, body: #"{R_GET}"(id: http!request.queryParameters.id))'


def content_files() -> dict[str, str]:
    lines = (f"{RT_LINE}?list", RT_NS)
    ui = {
        UI_LIST: (
            "EXP_ClaimsList",
            "Claims with a button to start a new one.",
            (),
            f"""a!localVariables(
  local!limit: #"{C_LIMIT}",
  {{
    {fn("recordActionField_v1")}(actions: {{ {fn("recordActionItem")}(action: #"urn:appian:record-action:v1:{RT}/{ACT_NEW}") }}),
    {fn("buttonWidget_v1")}(label: "Refresh", saveInto: {fn("startProcess3")}(processModel: #"{OUTSIDE_PM}", onSuccess: a!save(local!limit, #"{OUTSIDE_RULE}"()))),
    {fn("gridField_v1")}(
      data: {fn("recordData")}(recordType: {record(RT)}),
      columns: {{
        {fn("gridColumn")}(label: "Title", value: fv!row[{field(RT, F_TITLE)}]),
        {fn("gridColumn")}(label: "Amount", value: fv!row[{field(RT, F_AMOUNT)}])
      }}
    )
  }}
)""",
        ),
        UI_SUMMARY: (
            "EXP_ClaimSummary",
            "Record view of a claim.",
            (("record", RT, RT_NS),),
            f"""{fn("formLayout_v1")}(
  label: "Claim",
  contents: {{
    {fn("textField")}(label: "Title", value: ri!record[{field(RT, F_TITLE)}], readOnly: true),
    {fn("textField")}(label: "Status", value: ri!record[{field(RT, F_STATUS)}], readOnly: true),
  }}
)""",
        ),
        UI_CLAIM: (
            "EXP_ClaimForm",
            "Start form: a new claim.",
            (
                ("claim", RT, RT_NS),
                ("amount", "Decimal", T),
                ("receipt", "Document", T),
                ("lines", *lines),
            ),
            f"""{fn("formLayout_v1")}(
  label: "New expense claim",
  contents: {{
    {fn("textField")}(label: "Title", value: ri!claim[{field(RT, F_TITLE)}], saveInto: ri!claim[{field(RT, F_TITLE)}], required: true),
    {fn("floatingPointField")}(label: "Amount", value: ri!amount, saveInto: ri!amount, required: true),
    {fn("fileUploadField_v1")}(label: "Receipt", value: ri!receipt, saveInto: ri!receipt),
    #"{UI_LINES}"(lines: ri!lines),
    if(#"{R_NEEDS}"(amount: ri!amount), {fn("richTextDisplayField")}(value: "Needs approval"), {{}})
  }},
  buttons: {fn("ButtonLayout")}(primaryButtons: {{ {fn("ButtonWidgetSubmit")}(label: "Submit claim") }})
)""",
        ),
        UI_LINES: (
            "EXP_LineEditor",
            "One row per claim line.",
            (("lines", *lines),),
            f"""{fn("forEach")}(
  items: ri!lines,
  expression: {fn("textField")}(label: "Line description", value: fv!item[{field(RT_LINE, L_DESC)}], saveInto: ri!lines)
)""",
        ),
        UI_REVIEW: (
            "EXP_ReviewForm",
            "Task form: approve or reject.",
            (
                ("claim", RT, RT_NS),
                ("decision", "Text", T),
                ("comment", "Text", T),
                ("submitted", "Boolean", T),
            ),
            f"""{fn("formLayout_v1")}(
  label: "Review claim",
  contents: {{
    #"{UI_SUMMARY}"(record: ri!claim),
    {fn("sectionLayout_v1")}(label: "Decision", contents: {{
      {fn("radioButtonField_v1")}(choiceLabels: {{"Approve", "Reject"}}, choiceValues: {{"Approve", "Reject"}}, value: ri!decision, saveInto: ri!decision, required: true)
    }}),
    {fn("paragraphField")}(label: "Comment", value: ri!comment, saveInto: ri!comment, showWhen: ri!decision = "Reject")
  }},
  buttons: {fn("ButtonLayout")}(primaryButtons: {{ {fn("buttonWidget_v1")}(label: "Send", value: true, saveInto: ri!submitted, submit: true) }})
)""",
        ),
        UI_UNUSED: (
            "EXP_OldBanner",
            "Not used any more.",
            (),
            f'{fn("richTextDisplayField")}(value: "Old banner")',
        ),
        UI_DASH: (
            "EXP_Dashboard",
            "Totals for managers.",
            (),
            f'''a!localVariables(
  local!claims: #"{R_GET}"(id: 1),
  {fn("richTextDisplayField")}(label: "Lines total", value: #"{R_TOTAL}"(lines: local!claims[{field(RT, REL_LINES)}]))
)''',
        ),
    }
    out = {
        u: content("interface", n, u, inputs(*ins) + definition(sail), desc=d)
        for u, (n, d, ins, sail) in ui.items()
    }
    out[R_NEEDS] = content(
        "rule",
        "EXP_NeedsApproval",
        R_NEEDS,
        inputs(("amount", "Decimal", T)) + definition(f'if(ri!amount > #"{C_LIMIT}", true, false)'),
        desc="Claims above the limit need an approver.",
        tests=saved_tests(("small", {"amount": "100"}), ("large", {"amount": "900"})),
    )
    out[R_TOTAL] = content(
        "rule",
        "EXP_LineTotal",
        R_TOTAL,
        inputs(("lines", *lines))
        + definition(
            f"if({fn('isNullOrEmpty')}(ri!lines), 0, sum({fn('forEach')}(items: ri!lines, expression: fv!item[{field(RT_LINE, L_AMOUNT)}])))"
        ),
    )
    out[R_GET] = content(
        "rule",
        "EXP_GetClaim",
        R_GET,
        inputs(("id", "Integer", T))
        + definition(
            f'{fn("queryRecordType_v4")}(recordType: {record(RT)}, filters: {fn("queryFilter")}(field: {field(RT, F_ID)}, operator: "=", value: ri!id), pagingInfo: {fn("pagingInfo")}(1, 1)).data'
        ),
        tests=saved_tests(("existing", {"id": "42"})),
    )
    out[C_LIMIT] = content(
        "constant",
        "EXP_APPROVAL_LIMIT",
        C_LIMIT,
        constant("Integer", "500"),
        desc="Above this, a claim needs approval.",
    )
    out[INT_PAY] = content(
        "outboundIntegration",
        "EXP_PayClaim",
        INT_PAY,
        f"    <connectedSystemUuid>{CS}</connectedSystemUuid>\n",
        desc="Pays an approved claim.",
    )
    return out  # fmt: skip
