"""UAT scenarios in plain English, one per test path and per screen: the step before a spec.

Each scenario has preconditions (users, data, systems), numbered steps a tester follows, and
expected results. Values the export cannot tell (what a field should show, what the process
should have set) are listed as "to confirm": a person approves them before a spec is written.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from atg import mapdb, pathdb
from atg.testgen import forms, screens, sentences, testdata, urls

_TASK = "internal.17"
_SUBPROCESS = "internal.38"
_SKIP = {"core.0", "core.1", "core.2", "core.3", "core.4", "core.5"}  # start, end, gateways
_DOES = {
    "internal3.write_records": "saves records",
    "internal3.delete_records": "deletes records",
    "appian.system.smart-services.write-to-data-store": "saves to the database",
    "internal3.integration": "calls an outside system",
    "internal3.sendemail": "sends an email",
    "core.7": "waits on a timer",
}


def _names(items: list[dict[str, str]]) -> str:
    return ", ".join(i["name"] for i in items)


def path_scenario(con: sqlite3.Connection, sid: int, pm: str, no: int) -> dict[str, Any]:
    data = testdata.path_data(con, sid, pm, no)
    if "error" in data:
        return data
    n = mapdb.names(con, sid)
    stored = pathdb.read_one(con, sid, pm, no)
    assert stored is not None  # path_data above already found it
    steps_raw, decisions = stored.steps, stored.decisions
    nodes = {
        g: (t, lab or tn)
        for g, t, lab, tn in con.execute(
            "SELECT gui_id, type_id, label, type_name FROM nodes "
            "WHERE snapshot_id = ? AND pm_uuid = ?",
            (sid, pm),
        )
    }
    choice = {
        (d["gateway"], d["to"]): c for d, c in zip(decisions, data["conditions"], strict=True)
    }
    tasks = {t["task"]: t for t in data["user_tasks"]}
    task_screens = {
        r["where"].rsplit(" in ", 1)[0]: ui
        for ui, rs in screens.routes(con, sid).items()
        for r in rs
        if r["how"] == "user task" and r["owner"] == pm
    }
    start_ui = next(
        (
            ui
            for ui, rs in screens.routes(con, sid).items()
            if any(r["how"] == "start form" and r["owner"] == pm for r in rs)
        ),
        "",
    )
    form = n.objects[start_ui][1] if start_ui else ""
    steps = [sentences.how_started(con, sid, pm)]
    if form:
        found = forms.form_fields(con, sid, start_ui)
        fields = sentences.fills_text(
            [(v["name"], forms.fill_labels(found, v["name"])) for v in data["start_inputs"]]
        )
        steps.append(f"On the start form “{form}” fill in {fields} and submit.")
    auto: list[str] = []

    def flush() -> None:
        if auto:
            steps.append(f"The system runs on its own: {'; '.join(auto)}.")
            auto.clear()

    for i, g in enumerate(steps_raw):
        type_id, label = nodes.get(g, ("", f"node {g}"))
        nxt = steps_raw[i + 1] if i + 1 < len(steps_raw) else None
        if (g, nxt) in choice and choice[(g, nxt)]["needs"]:
            flush()
            c = choice[(g, nxt)]
            steps.append(
                f"At “{label}” the process takes “{c['choice']}”, "
                f"because {' and '.join(c['needs'])}."
            )
        elif type_id == _TASK:
            flush()
            t = tasks.get(label, {"groups": [], "fills": []})
            who = " or ".join(t["groups"]) or "the assigned user"
            fills = sentences.fills_text(
                [
                    (f["variable"], f.get("where", []))
                    for f in t["fills"]
                    if not any(w.startswith("button") for w in f.get("where", []))
                ]
            )
            clicks = [w for f in t["fills"] for w in f.get("where", []) if w.startswith("button")]
            ui = task_screens.get(label, "")
            files = " (attach a sample file)" if ui and screens.upload_fields(con, sid, ui) else ""
            steps.append(
                f"Log in as a user in {who}, open the task “{label}” from the task list "
                f"({urls.TASKS})"
                + (f", fill in {fills}" if fills else "")
                + files
                + (f" and click the {clicks[0]}." if clicks else " and submit.")
            )
        elif type_id == _SUBPROCESS:
            auto.append(f"“{label}” (a sub-process, tested in its own scenario)")
        elif type_id not in _SKIP:
            does = next((v for k, v in _DOES.items() if type_id.startswith(k)), "")
            auto.append(f"“{label}”" + (f" ({does})" if does else ""))
    flush()
    end = nodes.get(steps_raw[-1], ("", ""))[1] if steps_raw else ""
    groups = sorted({g for t in data["user_tasks"] for g in t["groups"]})
    pre = [f"A test user in each group: {', '.join(groups)}."] if groups else []
    pre += [
        f"{'Values to enter' if form else 'Start data'}: {v['name']} ({v['type']})"
        + (
            " — its fields are unknown, defined in another app."
            if v["kind"] == "outside this export"
            else "."
        )
        for v in data["start_inputs"]
    ]
    needs = list(dict.fromkeys(p for c in data["conditions"] for p in c["needs"]))
    pre += [f"Make sure that {p}." for p in needs]
    pre += sentences.rows_needed(data["records_read"])
    if data["outside_systems"]:
        pre.append(f"A test version (or fake) of {_names(data['outside_systems'])}.")
    expected = [f"The process ends at “{end}”." if end else "The process ends."]
    if data["records_written"]:
        expected.append(f"New or updated rows in {_names(data['records_written'])}.")
    if data["records_deleted"]:
        expected.append(f"Rows removed from {_names(data['records_deleted'])}.")
    started = sorted({s["name"] for s in data["subprocesses"]} - {"outside this export"})
    outside = sum(s["name"] == "outside this export" for s in data["subprocesses"])
    if started or outside:
        more = f" and {outside} process(es) from another app" if outside else ""
        expected.append(f"It starts {', '.join(started) or 'nothing in this export'}{more}.")
    confirm = [f"{c['variable']} after “{c['by']}”" for c in data["computed"]]
    route = " → ".join(d["rule"] for d in decisions) or "straight through"
    return {
        "title": f"{n.objects.get(pm, ('', pm))[1]}, path {no}: {route}",
        "preconditions": pre,
        "steps": steps,
        "expected": expected,
        "to_confirm": confirm,
    }


def screen_scenario(con: sqlite3.Connection, sid: int, uuid: str) -> dict[str, Any]:
    n = mapdb.names(con, sid)
    d = screens.screen_data(con, sid, uuid)
    name = n.objects.get(uuid, ("", uuid))[1]
    route = d["routes"][0] if d["routes"] else {"how": "", "where": ""}
    at = f" ({route['url']})" if route.get("url") else ""
    open_step = {
        "site page": f"Open the site page “{route['where']}”{at}.",
        "record view": f"Open a {route['where']} record from its list{at} and go to this view.",
        "user task": f"Reach the task {route['where']} and open it{at}.",
        "start form": f"Start {route['where']}{at}.",
    }.get(route["how"], "Open it directly in a test page (nothing in this export opens it).")
    pre = sentences.rows_needed(d["records_read"], "has rows in")
    pre += [
        f"Input {i['name']} ({i['type']}): try {', '.join(i['try'])}"
        + (f"; developers saved {', '.join(i['saved'])}" if i["saved"] else "")
        + "."
        for i in d["inputs"]
        if i["try"] or i["saved"]
    ]
    if d["file_uploads"]:
        pre.append(f"Sample files for its {d['file_uploads']} upload field(s).")
    steps = [open_step, "Check every field, label and list shows the test data."]
    steps += [f"Use “{a['label']}”: it {', '.join(a['does'])}." for a in d["actions"]]
    expected = ["The screen loads with no error."]
    if d["records_written"]:
        expected.append(f"New or updated rows in {_names(d['records_written'])}.")
    if d["records_deleted"]:
        expected.append(f"Rows removed from {_names(d['records_deleted'])}.")
    if route["how"] in {"user task", "start form"} and any(
        a["kind"] == "button" and "submits the form" in a["does"] for a in d["actions"]
    ):
        expected.append("Submitting moves the process on (see its path scenarios).")
    return {
        "title": f"Screen: {name}",
        "preconditions": pre,
        "steps": steps,
        "expected": expected,
        "to_confirm": [f"What {name} shows for the test data."],
    }
