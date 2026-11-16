"""Tools for working through the app: the census, actors, access check, lifecycle, the work
queue (resume, next_item, submit), feature drafts, use cases, test ideas and progress.

None of these lets the agent decide: approvals, merges, splits and authorisations are people's
(atg review, atg authorise, or the web tool).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from atg.agent import actors, census, doors, lifecycle, playbook, security
from atg.agent.atlas import Atlas
from atg.agent.cards import cut
from atg.analysis import brief, drafts, ledger, progress, queue, testideas, usecases


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict[str, str]  # name -> description; a trailing "?" in the name marks optional
    run: Callable[[Atlas, dict[str, Any]], dict[str, Any]]


def _json(value: Any) -> Any:
    """Arguments may arrive as JSON text (MCP strings, atg ask): decode them."""
    if isinstance(value, str) and value.strip()[:1] in "[{":
        return json.loads(value)
    return value


def _submit(at: Atlas, a: dict[str, Any]) -> dict[str, Any]:
    return ledger.submit(at, {k: _json(v) for k, v in a.items()})


def _work(name: str) -> Callable[[Atlas, dict[str, Any]], dict[str, Any]]:
    def run(at: Atlas, a: dict[str, Any]) -> dict[str, Any]:
        if name == "resume":
            return queue.resume(at)
        if name == "next_item":
            return ledger.next_item(at, str(a.get("draft", "")))
        if name == "progress":
            return progress.measures(at)
        if name == "drafts":
            return {
                "drafts": cut(
                    [
                        {k: d[k] for k in ("key", "name", "status", "reviewed", "summary")}
                        | {"doors": len(d["doors"]), "core": len(d["core"])}
                        | {"suggest": d["suggest"], "against": d["against"]}
                        for d in drafts.build(at)
                    ],
                    80,
                )
            }
        if name == "draft":
            return drafts.card(at, a["key"])
        if name == "use_cases":
            return {"use_cases": cut(usecases.build(at), 40)}
        return {"test_ideas": cut(testideas.build(at), 60)}

    return run


TOOLS = [
    Tool(
        "census",
        "What the map holds and cannot see: counts, gaps, what exports never contain.",
        {},
        lambda at, a: census.census(at),
    ),
    Tool(
        "actors",
        "Every kind of actor the export shows (groups, relationships, profile, API, "
        "timers) and the doors linked to each.",
        {},
        lambda at, a: {"actors": actors.actors(at)},
    ),
    Tool(
        "access_check",
        "Doors whose visibility and permission (role map) disagree.",
        {},
        lambda at, a: {"mismatches": security.check(doors.doors(at))},
    ),
    Tool(
        "lifecycle",
        "Each record type against create, read, update, delete and statuses set.",
        {},
        lambda at, a: {"record_types": lifecycle.lifecycle(at)},
    ),
    Tool(
        "resume",
        "Start of every session: counts by status, open questions, recent claims.",
        {},
        _work("resume"),
    ),
    Tool(
        "next_item",
        "Take the next work item (chosen by code) with its briefing and questions. With "
        "draft, only that draft's items, ending with its review.",
        {"draft?": "a draft key: work on this draft only"},
        _work("next_item"),
    ),
    Tool(
        "brief",
        "Everything about one feature draft at once: screens with labels, processes and "
        "tasks, data, rules, who may use it, related drafts, open work, naming hints.",
        {"key": "draft key or one of its door ids"},
        lambda at, a: brief.brief(at, a["key"]),
    ),
    Tool(
        "playbook",
        "How to review feature drafts: role lead (hands out drafts) or reviewer (one draft).",
        {"role": "lead or reviewer"},
        lambda at, a: playbook.playbook(str(a.get("role", "lead"))),
    ),
    Tool(
        "submit",
        "Finish an item: status, claims (each with evidence), reads. Claims are checked "
        "against the map; any failure refuses the whole submit.",
        {
            "item": "item id from next_item",
            "status": "done, done-partial, blocked or needs-human",
            "claims?": "JSON list of {subject, predicate, value, level, "
            "evidence: [{object, quote?, path?}]}",
            "reads?": "JSON list of {object, part?, truncated?, total?, resolved?}",
            "question?": "for needs-human: the question for a person",
            "note?": "short note",
            "model?": "model name",
        },
        _submit,
    ),
    Tool(
        "progress",
        "The ten progress measures with numerators, denominators and rules.",
        {},
        _work("progress"),
    ),
    Tool("drafts", "Feature drafts (proposals) with status and doubts.", {}, _work("drafts")),
    Tool(
        "draft",
        "One draft: doors, core, shared, why, against, unexplained, claims.",
        {"key": "draft key or one of its door ids"},
        _work("draft"),
    ),
    Tool("use_cases", "Use cases of approved features.", {}, _work("use_cases")),
    Tool(
        "test_ideas",
        "Test ideas of approved use cases, with where expected results come from.",
        {},
        _work("test_ideas"),
    ),
]
