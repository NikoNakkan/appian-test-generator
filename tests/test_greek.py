"""Greek (and other non-Latin) names: SAIL with Greek identifiers parses, and search folds case
and accents so "κατασταση" finds "Κατάσταση"."""

from __future__ import annotations

from atg.agent.states import statusish
from atg.sail import actions, fields
from atg.sail.ast import parse
from atg.sail.printer import print_node
from atg.textfold import fold, words

SAIL = (
    "a!localVariables(local!όνομα: ri!πελάτης.επώνυμο, Κλειδί: 1, "
    'a!textField(label: "Όνομα πελάτη", value: local!όνομα, saveInto: local!όνομα), '
    'a!buttonWidget(label: "Αποστολή", submit: true, saveInto: a!save(ri!κατάσταση, "Νέα")))'
)


def test_greek_identifiers_parse_and_round_trip() -> None:
    printed = print_node(parse(SAIL).root)
    assert "local!όνομα" in printed
    assert print_node(parse(printed).root) == printed


def test_greek_screen_gives_fields_and_buttons() -> None:
    found, _ = fields.find(SAIL)
    assert "Όνομα πελάτη" in [f.label for f in found]
    buttons = actions.find(SAIL)
    assert [b.label for b in buttons] == ["Αποστολή"]
    assert buttons[0].sets == ["κατάσταση"]


def test_fold_ignores_case_and_tonos() -> None:
    assert fold("Κατάσταση") == fold("ΚΑΤΑΣΤΑΣΗ") == "κατασταση"
    assert words("Αίτηση_Δαπάνης (νέα)") == "αιτηση δαπανησ νεα"  # final sigma folds to plain sigma
    assert statusish("Κατάσταση αίτησης")
    assert not statusish("Ποσό")
