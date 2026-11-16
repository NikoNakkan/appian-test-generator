"""Answers to GET views, kept until the map or its analysis file changes on disk.

A view is worked out from the map (and <map>.analysis.db) alone, so the same request on the
same files gives the same answer. The key holds each file's size and modification time, so an
import, a decision or a sheet upload makes every older answer unused. Small and bounded.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

MAX_ENTRIES = 64


def stamp(db: Path) -> tuple[tuple[int, int], ...]:
    """Size and modification time of the map, the analysis file and their journals."""
    analysis = db.with_name(db.stem + ".analysis.db")
    out = []
    for p in (db, analysis):
        for f in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-journal")):
            try:
                s = f.stat()
                out.append((s.st_size, s.st_mtime_ns))
            except OSError:
                out.append((-1, -1))
    return tuple(out)


class Answers:
    def __init__(self, db: Path) -> None:
        self.db = db
        self._lock = threading.Lock()
        self._kept: OrderedDict[tuple[Any, ...], Any] = OrderedDict()

    def get(self, key: tuple[Any, ...], work: Callable[[], Any]) -> Any:
        full = (key, stamp(self.db))
        with self._lock:
            if full in self._kept:
                self._kept.move_to_end(full)
                return self._kept[full]
        value = work()
        if stamp(self.db) == full[1]:  # nothing was written while it was worked out
            with self._lock:
                self._kept[full] = value
                while len(self._kept) > MAX_ENTRIES:
                    self._kept.popitem(last=False)
        return value
