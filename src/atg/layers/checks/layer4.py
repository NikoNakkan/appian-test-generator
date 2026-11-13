"""Layer 4 checks. Entry points and subprocess calls come from Layers 1 and 3 data, not from
the feature engine; the stored features must account for all of them."""

from __future__ import annotations

import json
import sqlite3

from atg.layers.checks.layer1 import CheckResult


def run(con: sqlite3.Connection, sid: int) -> list[CheckResult]:
    types = dict(con.execute("SELECT uuid, type FROM objects WHERE snapshot_id = ?", (sid,)))
    names = dict(con.execute("SELECT uuid, name FROM objects WHERE snapshot_id = ?", (sid,)))
    keys = {k for (k,) in con.execute("SELECT key FROM features WHERE snapshot_id = ?", (sid,))}
    members: dict[str, set[str]] = {}
    for key, uuid in con.execute(
        "SELECT key, uuid FROM feature_members WHERE snapshot_id = ?", (sid,)
    ):
        members.setdefault(key, set()).add(uuid)
    covered = set().union(*members.values()) if members else set()

    # 1. Every entry point whose target is in the export is listed, as itself, in a feature.
    recorded = {
        (e["owner"], e["kind"], e["name"], e["target"])
        for (entries,) in con.execute("SELECT entries FROM features WHERE snapshot_id = ?", (sid,))
        for e in json.loads(entries)
    }
    wanted = [
        (o, k, n, t)
        for o, k, n, t in con.execute(
            "SELECT owner_uuid, kind, name, target FROM entry_points WHERE snapshot_id = ?", (sid,)
        )
        if t in types
    ]
    wanted += [("", "web API", names[u], u) for u, t in types.items() if t == "webApi"]
    targets = wanted
    missing_entries = [f"{k} {n!r}" for o, k, n, t in wanted if (o, k, n, t) not in recorded]

    # 2. Every process belongs to some feature.
    processes = [u for u, t in types.items() if t == "processModel"]
    loose = [names[u] for u in processes if u not in covered]

    # 3. A process in a feature brings the subprocesses it calls (from the process nodes).
    calls = want = 0
    broken = []
    for pm, called in con.execute(
        "SELECT pm_uuid, calls FROM nodes WHERE snapshot_id = ? AND calls != ''", (sid,)
    ):
        if called not in types:
            continue  # a process in another app
        for key, ms in members.items():
            if pm in ms:
                want += 1
                if called in ms:
                    calls += 1
                else:
                    broken.append(f"{names.get(key, key)}: {names[pm]} -> {names[called]}")

    # 4. Every feature starts at a real object of this snapshot.
    invented = [k for k in keys if k not in types]
    return [
        CheckResult(
            "every entry point starts a feature",
            len(targets),
            len(targets) - len(missing_entries),
            missing_entries[:20],
        ),
        CheckResult(
            "every process is in a feature", len(processes), len(processes) - len(loose), loose[:20]
        ),
        CheckResult("features include the subprocesses they call", want, calls, broken[:20]),
        CheckResult(
            "every feature starts at a real object",
            len(keys),
            len(keys) - len(invented),
            invented[:20],
        ),
    ]
