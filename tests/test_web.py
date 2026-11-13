"""The local web tool: API shapes on the demo export, an import through HTTP end to end, and
requests from anywhere but this machine's own pages refused."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from atg import store
from atg.layers.pipeline import run_layers
from atg.web import api
from atg.web.server import App, make_handler
from tests.conftest import demo_export, single_root


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(tmp_path / "map.db")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url: str) -> Any:
    with urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def test_api_views_on_a_real_export(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    sid, results = run_layers(con, single_root(demo_export()))
    assert all(r.ok for r in results)

    snap = api.snapshots(con)[0]
    assert (snap["passed"], snap["checks"]) == (len(results), len(results))
    assert api.progress(con, sid)["layers"][0]["status"] == "passing"
    assert api.progress(con, sid)["layers"][1]["status"] == "passing"
    assert api.progress(con, sid)["layers"][2]["status"] == "passing"
    assert api.progress(con, sid)["layers"][3]["status"] == "passing"
    assert api.progress(con, sid)["layers"][4]["status"] == "not started"
    deps = api.dependencies(con, sid)
    assert deps["objects"] and deps["edges"]
    pm = api.processes(con, sid)[0]
    flow = api.process(con, sid, pm["uuid"])
    assert len(flow["nodes"]) == pm["nodes"]


def test_ratchet_compares_with_the_previous_import(tmp_path: Path) -> None:
    con = store.connect(tmp_path / "map.db")
    root = single_root(demo_export())
    run_layers(con, root)
    sid, _ = run_layers(con, root)
    rows = api.progress(con, sid)["ratchet"]
    assert rows and all(r["before"] == r["now"] for r in rows)


def test_import_over_http_runs_to_done(server: str) -> None:
    body = json.dumps({"path": str(demo_export())}).encode()
    req = Request(f"{server}/api/import", data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as r:
        job = json.loads(r.read())
    for _ in range(300):
        job = _get(f"{server}/api/jobs/{job['id']}")
        if job["state"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert job["state"] == "done", job["messages"]
    sid = job["snapshots"][0]
    assert all(c["ok"] for c in _get(f"{server}/api/snapshots/{sid}/checks"))
    with urlopen(f"{server}/", timeout=30) as r:
        assert b"Appian Test Generator" in r.read()


def test_bad_path_gives_a_clear_error(server: str) -> None:
    req = Request(f"{server}/api/import", data=b'{"path": "C:/nope/missing"}')
    with pytest.raises(Exception) as err:
        urlopen(req, timeout=30)
    assert "Can't find" in err.value.read().decode()  # type: ignore[attr-defined]


def _status(req: Request) -> int:
    try:
        with urlopen(req, timeout=30) as r:
            return int(r.status)
    except HTTPError as e:
        return int(e.code)


def test_other_hosts_and_cross_site_posts_are_refused(server: str) -> None:
    """DNS rebinding sends a foreign Host; a hostile page's POST carries a foreign Origin."""
    assert _status(Request(f"{server}/api/snapshots", headers={"Host": "evil.example"})) == 403
    body = json.dumps({"path": "C:/x"}).encode()
    post = Request(f"{server}/api/import", data=body, headers={"Origin": "http://evil.example"})
    assert _status(post) == 403
    assert _status(Request(f"{server}/api/snapshots")) == 200


def test_every_response_carries_security_headers(server: str) -> None:
    with urlopen(f"{server}/", timeout=30) as r:
        csp = r.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        page = r.read().decode()
    assert "http://" not in page and "https://" not in page  # nothing loaded from outside
