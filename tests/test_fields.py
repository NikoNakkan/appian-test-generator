"""Form fields by label, kind and bound input, as Playwright will look for them."""

from __future__ import annotations

from atg.sail.actions import find as find_actions
from atg.sail.fields import find
from atg.testgen.forms import fill_labels, task_form

CHILD = "_a-0000d3e0-0000-8000-9000-000000000000_63"


def test_fields_kinds_labels_and_inputs() -> None:
    fields, children = find(
        f"""{{
      #"SYSTEM_SYSRULES_textField"(label: "Title", value: ri!op.title, saveInto: ri!op.title,
        required: true),
      #"SYSTEM_SYSRULES_sectionLayout_v1"(label: "Acciones", contents: {{
        a!radioButtonField(choiceLabels: {{"Aprobar", "Rechazar"}}, choiceValues: {{1, 2}},
          value: ri!decision, saveInto: ri!decision, showWhen: ri!submitted)
      }}),
      a!dropdownField(label: local!titulo, value: ri!tipo),
      #"{CHILD}"(claimId: ri!op.id)
    }}"""
    )
    titulo, radio, dropdown = fields
    assert (titulo.kind, titulo.label, titulo.inputs, titulo.required) == (
        "text box",
        "Title",
        ["op"],
        True,
    )
    assert (radio.label, radio.choices, radio.conditional) == (
        "Acciones",
        ["Aprobar", "Rechazar"],
        True,
    )
    assert dropdown.computed_label and dropdown.label == "local!titulo"
    assert children[0].interface == CHILD and children[0].passes == {"claimId": ["op"]}


def test_fill_labels_and_task_form() -> None:
    fields = [
        {"kind": "text box", "label": "Title", "computed_label": False, "inputs": ["op"],
         "choices": []},
        {"kind": "radio buttons", "label": "", "computed_label": False, "inputs": ["decision"],
         "choices": ["Yes", "No"]},
    ]  # fmt: skip
    assert fill_labels(fields, "op") == ["“Title” (text box)"]
    assert fill_labels(fields, "decision") == ["the radio buttons (Yes / No)"]
    ui, inputs = task_form(f'#"{CHILD}"(submitted: ac!submitted, data: ac!claim)')
    assert ui == CHILD and inputs == {"submitted": "submitted", "data": "claim"}


def test_button_records_inputs_it_sets() -> None:
    (button,) = find_actions('a!buttonWidget(label: "Send", value: true, saveInto: ri!submitted)')
    assert button.sets == ["submitted"]
