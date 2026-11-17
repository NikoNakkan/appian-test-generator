"""Local web tool: import an export, watch it run, browse the results. Binds to 127.0.0.1 only."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from atg import approvals, store
from atg.web import (
    analysis_api,
    api,
    changes_api,
    designer_api,
    features_api,
    guard,
    paths_api,
    tests_api,
)
from atg.web.cache import Answers
from atg.web.jobs import Jobs

STATIC = Path(__file__).parent / "static"
_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 1024**3  # 1 GB
_SNAP = re.compile(r"^/api/snapshots/(\d+)/([\w-]+)$")
_JOB = re.compile(r"^/api/jobs/(\d+)$")
_UNCACHED = {"analysis"}  # shows work leases, which run out with time alone


def _int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


class App:
    def __init__(self, db: Path, base_url: str = "") -> None:
        self.db = db
        self.base_url = base_url
        self.uploads = db.parent / ".atg-uploads"
        self.jobs = Jobs(db)
        self.answers = Answers(db)
        store.connect(db).close()  # create the schema up front

    def con(self) -> sqlite3.Connection:
        return store.connect(self.db)


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # keep the console quiet
            pass

        def _refused(self, post: bool = False) -> bool:
            """Requests not from this machine's own pages get 403 (see guard.py)."""
            port = int(self.server.server_address[1])  # type: ignore[index]
            ok = guard.allowed_host(self.headers.get("Host"), port) and (
                not post or guard.allowed_origin(self.headers.get("Origin"), port)
            )
            if not ok:
                length = int(self.headers.get("Content-Length") or 0)
                if 0 < length <= 1024**2:
                    self.rfile.read(length)  # drain a small body so the client sees the answer
                self.close_connection = True
                self._error(HTTPStatus.FORBIDDEN, "Only this machine's own pages may use the tool.")
            return not ok

        def do_GET(self) -> None:
            if self._refused():
                return None
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if not url.path.startswith("/api/"):
                return self._static(url.path)
            if url.path == "/api/snapshots":
                return self._db(api.snapshots)
            if url.path == "/api/jobs":
                return self._json([j.to_json() for j in app.jobs.all()])
            if m := _JOB.match(url.path):
                job = app.jobs.get(int(m.group(1)))
                return self._json(job.to_json()) if job else self._error(404, "No such import.")
            if m := _SNAP.match(url.path):
                return self._snapshot(int(m.group(1)), m.group(2), query)
            self._error(404, "Unknown endpoint.")

        def do_POST(self) -> None:
            if self._refused(post=True):
                return None
            url = urlparse(self.path)
            if url.path == "/api/import":
                body = json.loads(self._body() or b"{}")
                path = Path(str(body.get("path", "")).strip().strip('"'))
                if not str(path) or not path.exists():
                    return self._error(
                        400, f"Can't find {path}. Paste the full folder or zip path."
                    )
                return self._json(app.jobs.start(path).to_json(), HTTPStatus.ACCEPTED)
            if url.path == "/api/upload":
                name = Path(parse_qs(url.query).get("name", ["export.zip"])[0]).name
                if not name.lower().endswith(".zip"):
                    return self._error(400, "Upload a .zip export, or paste a folder path instead.")
                data = self._body()
                stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                target = app.uploads / f"{stamp}-{name}"
                app.uploads.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                return self._json(app.jobs.start(target).to_json(), HTTPStatus.ACCEPTED)
            if (m := _SNAP.match(url.path)) and m.group(2) == "decision":
                body = json.loads(self._body() or b"{}")
                sid = int(m.group(1))
                return self._db(lambda c: analysis_api.decision(c, sid, body))
            if (m := _SNAP.match(url.path)) and m.group(2) == "features-sheet":
                con = app.con()
                try:
                    result = approvals.import_sheet(con, int(m.group(1)), self._body())
                finally:
                    con.close()
                return self._json(asdict(result))
            self._error(404, "Unknown endpoint.")

        def _snapshot(self, sid: int, what: str, query: dict[str, str]) -> None:
            views: dict[str, Callable[[sqlite3.Connection], Any]] = {
                "checks": lambda c: api.checks(c, sid),
                "progress": lambda c: api.progress(c, sid),
                "dependencies": lambda c: api.dependencies(c, sid),
                "processes": lambda c: api.processes(c, sid),
                "process": lambda c: api.process(c, sid, query.get("uuid", "")),
                "decisions": lambda c: paths_api.decisions(c, sid, query.get("uuid", "")),
                "paths": lambda c: paths_api.paths(
                    c, sid, query.get("uuid", ""), _int(query.get("path"))
                ),
                "test-users": lambda c: paths_api.test_users(c, sid),
                "features": lambda c: approvals.feature_list(c, sid),
                "feature": lambda c: features_api.feature(c, sid, query.get("key", "")),
                "outside-entries": lambda c: features_api.outside(c, sid),
                "object": lambda c: designer_api.object_page(c, sid, query.get("uuid", "")),
                "node": lambda c: designer_api.node_page(
                    c, sid, query.get("uuid", ""), int(query.get("gui", "-1") or -1)
                ),
                "tests": lambda c: tests_api.tests(c, sid),
                "scenario": lambda c: tests_api.scenario(
                    c, sid, query.get("uuid", ""), _int(query.get("path"))
                ),
                "test-data": lambda c: tests_api.test_data(
                    c, sid, query.get("uuid", ""), _int(query.get("path"))
                ),
                **analysis_api.views(sid, query, app.base_url),
                "changes": lambda c: changes_api.changes(c, sid, _int(query.get("base"))),
                "object-diff": lambda c: changes_api.object_diff(
                    c, sid, _int(query.get("base")) or 0, query.get("uuid", "")
                ),
            }
            if what == "features-sheet":
                con = app.con()
                try:
                    data = approvals.export_sheet(con, sid)
                finally:
                    con.close()
                return self._send(data, _XLSX, filename=f"features-snapshot-{sid}.xlsx")
            if what not in views:
                return self._error(404, "Unknown view.")
            if what in _UNCACHED:
                return self._db(views[what])
            key = (sid, what, tuple(sorted(query.items())))
            self._db(lambda c: app.answers.get(key, lambda: views[what](c)))

        def _db(self, fn: Callable[[sqlite3.Connection], Any]) -> None:
            con = app.con()
            try:
                self._json(fn(con))
            finally:
                con.close()

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                raise ValueError("upload too large")
            return self.rfile.read(length)

        def _static(self, path: str) -> None:
            file = (STATIC / (path.lstrip("/") or "index.html")).resolve()
            if STATIC.resolve() not in file.parents or not file.is_file():
                return self._error(404, "Not found.")
            self._send(file.read_bytes(), _TYPES.get(file.suffix, "application/octet-stream"))

        def _json(self, data: Any, status: int = HTTPStatus.OK) -> None:
            self._send(json.dumps(data).encode("utf-8"), "application/json", status)

        def _error(self, status: int, message: str) -> None:
            self._json({"error": message}, status)

        def _send(
            self, body: bytes, ctype: str, status: int = HTTPStatus.OK, filename: str = ""
        ) -> None:
            self.send_response(status)
            text = ctype.startswith(("text/", "application/json"))
            self.send_header("Content-Type", f"{ctype}; charset=utf-8" if text else ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in guard.SECURITY_HEADERS.items():
                self.send_header(name, value)
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(db: Path, port: int, base_url: str = "") -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(db, base_url)))
    print(f"Appian test generator running at http://127.0.0.1:{port}  (map: {db})")
    server.serve_forever()
