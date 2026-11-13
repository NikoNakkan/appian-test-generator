"""Frozen golden sample of the demo export. Skipped until a human has approved
tests/golden/demo.json (regenerate with python -m scripts.make_golden)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atg.golden import DEMO_GOLDEN, extract
from atg.read.ingest import read_snapshot
from tests.conftest import demo_export, single_root

GOLDEN = Path(__file__).parent / "golden" / "demo.json"


def test_golden_sample_unchanged() -> None:
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if not doc["approved_by"]:
        pytest.skip("golden sample not approved yet: review tests/golden/demo-review.md")
    current = extract(read_snapshot(single_root(demo_export())), DEMO_GOLDEN)
    assert current == doc["objects"]
