"""A small, made-up Appian 25.4 export for tests: "Expense Claims". No real app's data.

    build(folder) writes it; `python -m tests.demo <folder>` does the same from the shell.

What it covers, so every layer has something real to read:
  processes   EXP_SubmitClaim: start form, 2 gateways (rules + defaults), a user task with a
              form and a group, write records, an integration call, a sub-process (3 paths);
              EXP_Notify (script task), EXP_Withdraw (related action)
  screens     a site page (record action button, a button starting a process from another app,
              a grid of records), a record view, a start form with a child interface and a
              file upload, a task form (radio buttons in a section, a button setting an input),
              one interface nothing opens
  rules       an if() against a constant (saved tests), a loop with an empty check, a query
  records     claims and their lines: table, daily sync, relationships, a computed field,
              a record list action and a related action
  entries     2 site pages and a task report page, a list and a related action, a web API
  outside     a rule, a process and a task report that live in another app
"""

from __future__ import annotations

from pathlib import Path

from tests.demo import content, spec
from tests.demo.process import process
from tests.demo.xml import datatype, record_type, simple, site, web_api


def build(folder: Path) -> Path:
    """Write the export into folder (created) and return it."""
    files: dict[str, str] = {
        "META-INF/MANIFEST.MF": "Manifest-Version: 1.0\nAppian-Version: 25.4.0.0\n"
    }
    for haul, kind, name, uuid, extra in spec.SIMPLE:
        files[f"{haul.removesuffix('Haul')}/{uuid}.xml"] = simple(haul, kind, name, uuid, extra)
    for uuid, text in content.content_files().items():
        files[f"content/{uuid}.xml"] = text
    for rt in spec.RECORD_TYPES:
        files[f"recordType/{rt['uuid']}.xml"] = record_type(rt)
    for pm in spec.processes():
        files[f"processModel/{pm['uuid']}.xml"] = process(
            pm, lambda g, u=pm["uuid"]: spec.node_uuid(u, g)
        )
    files[f"webApi/{spec.WEB_API}.xml"] = web_api(
        spec.WEB_API, "EXP_ClaimStatusApi", "claim-status", "GET", content.API_SAIL
    )
    files[f"site/{spec.SITE}.xml"] = site(spec.SITE, "EXP_Portal", "expenses", spec.PAGES)
    files["datatype/%7Burn%3Acom%3Aappian%3Atypes%3AEXP%7DEXP_Payment.xsd"] = datatype(
        "urn:com:appian:types:EXP", "EXP_Payment", [("reference", "string"), ("paidOn", "date")]
    )
    for rel, text in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return folder


# Three realistic edits for regression tests (and to try the Changes view): a constant's value,
# a gateway condition, and a rule's result for empty input.
NEXT_RELEASE = [
    (f"content/{spec.C_LIMIT}.xml", "<value>500</value>", "<value>1000</value>"),
    (f"processModel/{spec.PM_SUBMIT}.xml", '=pv!decision = "Approve"', '=pv!decision = "Approved"'),
    (f"content/{spec.R_TOTAL}.xml", "ri!lines), 0, sum(", "ri!lines), null, sum("),
]


def build_next(folder: Path) -> Path:
    """The same app one release later: build() plus the NEXT_RELEASE edits."""
    build(folder)
    for rel, old, new in NEXT_RELEASE:
        path = folder / rel
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, (rel, old)
        path.write_text(text.replace(old, new), encoding="utf-8")
    return folder
