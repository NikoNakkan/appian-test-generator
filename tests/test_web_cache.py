"""Kept answers are reused only while the map and its analysis file are unchanged."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atg.web.cache import Answers


def test_reuse_until_a_file_changes(tmp_path: Path) -> None:
    db = tmp_path / "map.db"
    sqlite3.connect(db).close()
    answers = Answers(db)
    calls: list[int] = []

    def work() -> int:
        calls.append(1)
        return len(calls)

    assert answers.get(("a",), work) == 1
    assert answers.get(("a",), work) == 1  # kept
    assert answers.get(("b",), work) == 2  # another view
    con = sqlite3.connect(tmp_path / "map.analysis.db")  # a decision creates or writes it
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    assert answers.get(("a",), work) == 3
