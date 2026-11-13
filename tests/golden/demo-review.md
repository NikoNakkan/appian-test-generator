# Layer 1 golden sample — please review

For each object: does the extracted list match the raw code below it?
When all 5 are right, set `approved_by` in `demo.json` to your name.

## rule: EXP_GetClaim

File: `content/_a-0000d3e0-0000-8000-9000-000000000000_72.xml`

| kind | target | points to | uses |
|---|---|---|---|
| record_type | `d3e0000a-0000-4000-8000-00000000000a` | recordType EXP_Claim | 2 |

Built-in functions: pagingInfo x1, queryFilter x1, queryRecordType_v4 x1

<details><summary>Raw code</summary>

```
#"SYSTEM_SYSRULES_queryRecordType_v4"(recordType: #"urn:appian:record-type:v1:d3e0000a-0000-4000-8000-00000000000a", filters: #"SYSTEM_SYSRULES_queryFilter"(field: #"urn:appian:record-field:v1:d3e0000a-0000-4000-8000-00000000000a/d3e0000b-0000-4000-8000-00000000000b", operator: "=", value: ri!id), pagingInfo: #"SYSTEM_SYSRULES_pagingInfo"(1, 1)).data
```

</details>

## interface: EXP_ReviewForm

File: `content/_a-0000d3e0-0000-8000-9000-000000000000_64.xml`

| kind | target | points to | uses |
|---|---|---|---|
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_61` | interface EXP_ClaimSummary | 1 |
| xml | `d3e0000a-0000-4000-8000-00000000000a` | recordType EXP_Claim | 1 |

Built-in functions: ButtonLayout x1, buttonWidget_v1 x1, formLayout_v1 x1, paragraphField x1, radioButtonField_v1 x1, sectionLayout_v1 x1

<details><summary>Raw code</summary>

```
#"SYSTEM_SYSRULES_formLayout_v1"(
  label: "Review claim",
  contents: {
    #"_a-0000d3e0-0000-8000-9000-000000000000_61"(record: ri!claim),
    #"SYSTEM_SYSRULES_sectionLayout_v1"(label: "Decision", contents: {
      #"SYSTEM_SYSRULES_radioButtonField_v1"(choiceLabels: {"Approve", "Reject"}, choiceValues: {"Approve", "Reject"}, value: ri!decision, saveInto: ri!decision, required: true)
    }),
    #"SYSTEM_SYSRULES_paragraphField"(label: "Comment", value: ri!comment, saveInto: ri!comment, showWhen: ri!decision = "Reject")
  },
  buttons: #"SYSTEM_SYSRULES_ButtonLayout"(primaryButtons: { #"SYSTEM_SYSRULES_buttonWidget_v1"(label: "Send", value: true, saveInto: ri!submitted, submit: true) })
)
```

</details>

## constant: EXP_APPROVAL_LIMIT

File: `content/_a-0000d3e0-0000-8000-9000-000000000000_80.xml`

| kind | target | points to | uses |
|---|---|---|---|
| — | — | no references | — |

<details><summary>Raw code</summary>

```
<?xml version="1.0" encoding="UTF-8"?>
<contentHaul xmlns:a="http://www.appian.com/ae/types/2009">
  <constant>
    <name>EXP_APPROVAL_LIMIT</name>
    <uuid>_a-0000d3e0-0000-8000-9000-000000000000_80</uuid>
    <description>Above this, a claim needs approval.</description>
    <typedValue><type><name>Integer</name><namespace>http://www.appian.com/ae/types/2009</namespace></type><value>500</value></typedValue>
  </constant>
</contentHaul>

```

</details>

## recordType: EXP_Claim

File: `recordType/d3e0000a-0000-4000-8000-00000000000a.xml`

| kind | target | points to | uses |
|---|---|---|---|
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_61` | interface EXP_ClaimSummary | 1 |
| xml | `d3e00014-0000-4000-8000-000000000014` | recordType EXP_ClaimLine | 1 |
| xml | `d3e00032-0000-4000-8000-000000000032` | processModel EXP_SubmitClaim | 1 |
| xml | `d3e00034-0000-4000-8000-000000000034` | processModel EXP_Withdraw | 1 |

<details><summary>Raw code</summary>

```
<?xml version="1.0" encoding="UTF-8"?>
<recordTypeHaul xmlns:a="http://www.appian.com/ae/types/2009" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <recordType a:uuid="d3e0000a-0000-4000-8000-00000000000a" name="EXP_Claim">
    <a:urlStub>claims</a:urlStub>
    <a:detailViewCfg><a:nameExpr>Summary</a:nameExpr><a:uiExpr>#"_a-0000d3e0-0000-8000-9000-000000000000_61"(record: rv!record)</a:uiExpr><a:urlStub>summary</a:urlStub></a:detailViewCfg>
    <a:recordListActionCfg a:uuid="d3e00011-0000-4000-8000-000000000011"><a:staticTitle>New claim</a:staticTitle><a:target a:uuid="d3e00032-0000-4000-8000-000000000032" xsi:type="a:ProcessModel"/><a:visibilityExpr/></a:recordListActionCfg>
    <a:relatedActionCfg a:uuid="d3e00012-0000-4000-8000-000000000012"><a:staticTitleString>Withdraw</a:staticTitleString><a:target a:uuid="d3e00034-0000-4000-8000-000000000034" xsi:type="a:ProcessModel"/><a:visibilityExpr/></a:relatedActionCfg>
    <a:recordRelationshipCfg><uuid>d3e00010-0000-4000-8000-000000000010</uuid><relationshipName>lines</relationshipName><targetRecordTypeUuid>d3e00014-0000-4000-8000-000000000014</targetRecordTypeUuid><relationshipType>ONE_TO_MANY</relationshipType></a:recordRelationshipCfg>
    <a:sourceConfiguration><sourceUuid>exp_claim@jdbc/Demo</sourceUuid><sourceType>RDBMS_TABLE</sourceType><friendlyName>exp_claim</friendlyName>
      <field><uuid>d3e0000b-0000-4000-8000-00000000000b</uuid><type>{http://www.appian.com/ae/types/2009}Integer</type><sourceFieldName>id</sourceFieldName><fieldName>id</fieldName><isRecordId>true</isRecordId><isCustomField>false</isCustomField></field>
      <field><uuid>d3e0000c-0000-4000-8000-00000000000c</uuid><type>{http://www.appian.com/ae/types/2009}Text</type><sourceFieldName>title</sourceFieldName><fieldName>title</fieldName><isRecordId>false</isRecordId><isCustomField>false</isCustomField></field>
      <field><uuid>d3e0000d-0000-4000-8000-00000000000d</uuid><type>{http://www.appian.com/ae/types/2009}Decimal</type><sourceFieldName>amount</sourceFieldName><fieldName>amount</fieldName><isRecordId>false</isRecordId><isCustomField>false</isCustomField></field>
      <field><uuid>d3e0000e-0000-4000-8000-00000000000e</uuid><type>{http://www.appian.com/ae/types/2009}Text</type><sourceFieldName>status</sourceFieldName><fieldName>status</fieldName><isRecordId>false</isRecordId><isCustomField>false</isCustomField></field>
      <field><uuid>d3e0000f-0000-4000-8000-00000000000f</uuid><type>{http://www.appian.com/ae/types/2009}Decimal</type><sourceFieldName></sourceFieldName><fieldName>amountWithTax</fieldName><isRecordId>false</isRecordId><isCustomField>true</isCustomField><customFieldExpr>rv!record[#"urn:appian:record-field:v1:d3e0000a-0000-4000-8000-00000000000a/d3e0000d-0000-4000-8000-00000000000d"] * 1.2</customFieldExpr></field>
      <refreshSchedule><frequency>DAILY</frequency><value>{"hour":2,"minute":"00","amPM":"AM"}</value><activated>true</activated></refreshSchedule>
    </a:sourceConfiguration>
  </recordType>
</recordTypeHaul>

```

</details>

## processModel: EXP_SubmitClaim

File: `processModel/d3e00032-0000-4000-8000-000000000032.xml`

| kind | target | points to | uses |
|---|---|---|---|
| record_type | `d3e0000a-0000-4000-8000-00000000000a` | recordType EXP_Claim | 1 |
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_31` | integration EXP_PayClaim | 1 |
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_62` | interface EXP_ClaimForm | 1 |
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_64` | interface EXP_ReviewForm | 1 |
| sail | `_a-0000d3e0-0000-8000-9000-000000000000_70` | rule EXP_NeedsApproval | 1 |
| xml | `_a-0000d3e0-0000-8000-9000-000000000000_62` | interface EXP_ClaimForm | 1 |
| xml | `_a-0000d3e0-0000-8000-9000-000000000000_64` | interface EXP_ReviewForm | 1 |
| xml | `d3e00003-0000-4000-8000-000000000003` | group EXP_Approvers | 1 |
| xml | `d3e0000a-0000-4000-8000-00000000000a` | recordType EXP_Claim | 1 |
| xml | `d3e00033-0000-4000-8000-000000000033` | processModel EXP_Notify | 1 |

Nodes (guiId, type, label):

- 0: Start Event (`core.0`) 'Start'
- 1: XOR (`core.4`) 'Needs approval?'
- 2: User Input Task (`internal.17`) 'Review claim'
- 3: XOR (`core.4`) 'Approved?'
- 4: Write Records (`internal3.write_records_to_source_23r3`) 'Save claim'
- 5: Sub-Process (`internal.38`) 'Tell employee'
- 6: Call Integration (`internal3.integration`) 'Pay claim'
- 7: End Event (`core.1`) 'End'

Flows (from → to, kind, label, condition):

- 0 → 1 connection '' ``
- 1 → 2 connection '' ``
- 1 → 4 connection '' ``
- 1 → 4 gateway_default '' ``
- 1 → 2 gateway_rule 'Yes' `=#"_a-0000d3e0-0000-8000-9000-000000000000_70"(amount: pv!amount)`
- 2 → 3 connection '' ``
- 3 → 4 connection '' ``
- 3 → 5 connection '' ``
- 3 → 5 gateway_default '' ``
- 3 → 4 gateway_rule 'Approved' `=pv!decision = "Approve"`
- 4 → 6 connection '' ``
- 5 → 7 connection '' ``
- 6 → 7 connection '' ``

<details><summary>Raw code</summary>

```
=#"_a-0000d3e0-0000-8000-9000-000000000000_70"(amount: pv!amount)
---
=pv!decision = "Approve"
---
=a!update(pv!claim, #"urn:appian:record-field:v1:d3e0000a-0000-4000-8000-00000000000a/d3e0000e-0000-4000-8000-00000000000e", "Approved")
---
=#"_a-0000d3e0-0000-8000-9000-000000000000_31"(claimId: pv!claim)
```

</details>
