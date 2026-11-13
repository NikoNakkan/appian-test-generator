"""Golden sample: what Layer 1 extracted for a few objects, in a form a human can check once.

The approved JSON is then frozen and compared on every test run.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from atg.model import AppObject, RefKind, Snapshot
from atg.read.link import resolvable_targets

# One object of each main kind in the demo export (tests/demo).
DEMO_GOLDEN = {
    "_a-0000d3e0-0000-8000-9000-000000000000_72": "rule",
    "_a-0000d3e0-0000-8000-9000-000000000000_64": "interface",
    "_a-0000d3e0-0000-8000-9000-000000000000_80": "constant",
    "d3e0000a-0000-4000-8000-00000000000a": "recordType",
    "d3e00032-0000-4000-8000-000000000032": "processModel",
}


def extract(snap: Snapshot, uuids: dict[str, str]) -> dict[str, Any]:
    by_uuid = {o.uuid: o for o in snap.objects}
    targets = resolvable_targets(snap.objects)
    return {u: _describe(by_uuid[u], by_uuid, targets) for u in uuids}


def _describe(o: AppObject, by_uuid: dict[str, AppObject], targets: set[str]) -> dict[str, Any]:
    refs = Counter(
        (r.kind.value, r.target)
        for r in o.references
        if r.kind not in (RefKind.PLATFORM, RefKind.SELF)
    )
    platform = Counter(r.target for r in o.references if r.kind is RefKind.PLATFORM)
    return {
        "type": o.type,
        "name": o.name,
        "path": o.path,
        "content_hash": o.content_hash,
        "references": [
            {"kind": k, "target": t, "points_to": _points_to(t, by_uuid, targets), "uses": n}
            for (k, t), n in sorted(refs.items())
        ],
        "platform_functions": dict(sorted(platform.items())),
        "internal_ids": len(o.internal_ids),
        "nodes": [[n.gui_id, n.type_id, n.type_name, n.label] for n in o.nodes],
        "flows": [[f.from_gui, f.to_gui, f.kind.value, f.label, f.condition] for f in o.flows],
    }


def _points_to(target: str, by_uuid: dict[str, AppObject], targets: set[str]) -> str:
    if target in by_uuid:
        return f"{by_uuid[target].type} {by_uuid[target].name}"
    return "internal id of another object" if target in targets else "EXTERNAL (not in export)"


def review_markdown(golden: dict[str, Any], raw_excerpts: dict[str, str]) -> str:
    lines = [
        "# Layer 1 golden sample — please review",
        "",
        "For each object: does the extracted list match the raw code below it?",
        "When all 5 are right, set `approved_by` in `demo.json` to your name.",
        "",
    ]
    for uuid, g in golden.items():
        lines += [f"## {g['type']}: {g['name']}", "", f"File: `{g['path']}`", ""]
        lines += ["| kind | target | points to | uses |", "|---|---|---|---|"]
        lines += [
            f"| {r['kind']} | `{r['target']}` | {r['points_to']} | {r['uses']} |"
            for r in g["references"]
        ] or ["| — | — | no references | — |"]
        if g["platform_functions"]:
            lines += [
                "",
                "Built-in functions: "
                + ", ".join(
                    f"{k.replace('SYSTEM_SYSRULES_', '')} x{v}"
                    for k, v in g["platform_functions"].items()
                ),
            ]
        if g["nodes"]:
            lines += ["", "Nodes (guiId, type, label):", ""]
            lines += [f"- {n[0]}: {n[2]} (`{n[1]}`) {n[3]!r}" for n in g["nodes"]]
            lines += ["", "Flows (from → to, kind, label, condition):", ""]
            lines += [f"- {f[0]} → {f[1]} {f[2]} {f[3]!r} `{f[4]}`" for f in g["flows"]]
        lines += [
            "",
            "<details><summary>Raw code</summary>",
            "",
            "```",
            raw_excerpts[uuid],
            "```",
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines)
