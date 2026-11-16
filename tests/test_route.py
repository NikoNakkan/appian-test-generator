"""Where each item starts in the running app: address, who to log in as, the clicks, and for a
task the doors that start its process."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atg.agent import atlas, doors, route, tools
from tests.conftest_agent import fresh
from tests.demo import spec

BASE = "https://appian.example.com"


@pytest.fixture
def at(tmp_path: Path) -> atlas.Atlas:
    a = fresh(tmp_path)
    a.memo["base_url"] = BASE + "/"
    return a


def first(at: atlas.Atlas, kind: str) -> dict[str, Any]:
    return next(d for d in doors.doors(at) if d["kind"] == kind)


def test_a_page_route_is_a_full_link(at: atlas.Atlas) -> None:
    r = route.route(at, doors.by_id(at, f"page:{spec.SITE}:claims") or {})
    assert r["open"].startswith(BASE + "/suite/sites/") and r["open"] in r["steps"][0]
    assert "note" not in r


def test_a_task_says_what_to_start_first(at: atlas.Atlas) -> None:
    r = route.route(at, first(at, "user task"))
    assert r["steps"][0].startswith("First make the task exist")
    assert r["first"] and r["log_in_as"].startswith("a member of")
    assert r["open"] == BASE + "/suite/tempo/tasks"


def test_a_timer_has_nothing_to_click(at: atlas.Atlas) -> None:
    r = route.route(at, first(at, "timer start"))
    assert r["log_in_as"].startswith("nobody") and "timer" in r["steps"][0]


def test_items_and_cards_carry_the_route(at: atlas.Atlas) -> None:
    item = tools.call(at, "next_item", {})
    assert item["kind"] == "assess_entry" and item["start_here"]["steps"]
    card = tools.call(at, "card", {"id": item["subject"]})
    assert card["start_here"]["door"] == item["subject"]


def test_without_a_base_url_it_says_so(tmp_path: Path) -> None:
    at = fresh(tmp_path)
    r = route.route(at, doors.by_id(at, f"page:{spec.SITE}:claims") or {})
    assert r["open"].startswith("/suite/") and "Appian address" in r["note"]
