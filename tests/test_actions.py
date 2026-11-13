"""Screen actions from SAIL in both spellings: a!... and Appian's internal SYSTEM_SYSRULES names."""

from __future__ import annotations

from atg.sail.actions import find

RT = "91b70937-07ac-4038-be6e-fe2336bc5559"
ACTION = "77e2ddf9-4e13-495f-958d-71cc140a6388"
PM = "_a-0000ed5f-a333-8000-9d18-011c48011c48_10344720"


def test_internal_names_are_recognised() -> None:
    src = f"""{{
      #"SYSTEM_SYSRULES_ButtonWidgetSubmit"(label: "Enviar"),
      #"SYSTEM_SYSRULES_buttonWidget_v1"(label: "refrescar",
        saveInto: #"SYSTEM_SYSRULES_startProcess3"(
          processModel: #"{PM}", onSuccess: a!save(local!x, 1))),
      #"SYSTEM_SYSRULES_buttonWidget_v1"(label: "Guardar", submit: true(),
        saveInto: #"SYSTEM_SYSRULES_writeRecords_v2"(
          records: #"urn:appian:record-type:v1:{RT}"(id: 1)))
    }}"""
    by = {a.label: a for a in find(src)}
    assert by["Enviar"].submits
    assert by["refrescar"].starts == [PM] and by["refrescar"].saves == 1
    assert by["Guardar"].submits and by["Guardar"].writes == [RT]


def test_record_action_item_and_plain_links() -> None:
    src = f"""{{
      #"SYSTEM_SYSRULES_recordActionItem"(action: #"urn:appian:record-action:v1:{RT}/{ACTION}"),
      a!dynamicLink(label: "just navigate", saveInto: local!page),
      a!startProcessLink(label: "Go", processModel: #"{PM}")
    }}"""
    found = find(src)
    assert [a.kind for a in found] == ["record action", "process link"]
    assert found[0].record_actions == [f"{RT}/{ACTION}"] and found[1].starts == [PM]


def test_broken_source_gives_nothing() -> None:
    assert find("a!buttonWidget(((") == []
