"""Background import jobs: one thread per export, progress readable while it runs."""

from __future__ import annotations

import itertools
import threading
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from atg import store
from atg.layers.pipeline import run_layers
from atg.read.select import UnsupportedVersionError
from atg.read.source import find_roots


@dataclass
class Job:
    id: int
    source: str
    state: str = "queued"  # queued | running | done | failed
    stage: str = ""
    done: int = 0
    total: int = 0
    root: str = ""
    snapshots: list[int] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class Jobs:
    def __init__(self, db: Path) -> None:
        self._db = db
        self._jobs: dict[int, Job] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def start(self, source: Path) -> Job:
        with self._lock:
            job = Job(next(self._ids), str(source))
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, source), daemon=True).start()
        return job

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: -j.id)

    def _run(self, job: Job, source: Path) -> None:
        job.state = "running"
        try:
            roots = find_roots(source)
            if not roots:
                raise ValueError("No Appian export found there (no META-INF/MANIFEST.MF).")
            con = store.connect(self._db)
            for root in roots:
                job.root = f"{root.path.name} (Appian {root.appian_version})"
                try:
                    sid, results = run_layers(
                        con, root, progress=lambda s, d, t: _set(job, s, d, t)
                    )
                except UnsupportedVersionError as e:
                    job.messages.append(f"Skipped: {e}")
                    continue
                job.snapshots.append(sid)
                failed = [r.name for r in results if not r.ok]
                job.messages.append(
                    f"Snapshot {sid}: {len(results) - len(failed)}/{len(results)} checks pass"
                    + (f" (failing: {', '.join(failed)})" if failed else "")
                )
            con.close()
            job.state = "done" if job.snapshots else "failed"
        except Exception as e:  # report any failure to the UI instead of dying silently
            job.state = "failed"
            job.messages.append(str(e) or traceback.format_exc(limit=1))


def _set(job: Job, stage: str, done: int, total: int) -> None:
    job.stage, job.done, job.total = stage, done, total
