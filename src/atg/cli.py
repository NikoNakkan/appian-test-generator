"""atg ingest <export> [--db map.db] — read exports into the map and run the Layer 1 checks."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from atg import store
from atg.layers import path_engine
from atg.layers.pipeline import run_layers
from atg.read.select import UnsupportedVersionError
from atg.read.source import find_roots

_BASE_HELP = "your Appian address (https://...), so routes give full links"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="read an export (folder or zip) into the map")
    ing.add_argument("export", type=Path)
    ing.add_argument("--db", type=Path, default=Path("map.db"))
    ing.add_argument(
        "--max-paths",
        type=int,
        default=None,
        help=f"test paths kept per process (default {path_engine.MAX_PATHS:,})",
    )
    chg = sub.add_parser(
        "changes", help="what changed since an earlier import, and which tests to run"
    )
    chg.add_argument("--db", type=Path, default=Path("map.db"))
    chg.add_argument("--head", type=int, help="newer snapshot (default: the latest)")
    chg.add_argument(
        "--base", type=int, help="older snapshot (default: previous import of the app)"
    )
    srv = sub.add_parser("serve", help="open the local web tool")
    srv.add_argument("--db", type=Path, default=Path("map.db"))
    srv.add_argument("--port", type=int, default=8777)
    srv.add_argument("--base-url", default=os.environ.get("ATG_BASE_URL", ""), help=_BASE_HELP)
    for name, help_ in (
        ("mcp", "serve the map to an AI agent over MCP (stdio)"),
        ("ask", "call one agent tool and print its JSON"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--db", type=Path, default=Path("map.db"))
        p.add_argument("--snapshot", type=int, help="default: the latest import")
        p.add_argument("--base-url", default=os.environ.get("ATG_BASE_URL", ""), help=_BASE_HELP)
        if name == "ask":
            p.add_argument("tool")
            p.add_argument("args", nargs="?", default="{}", help='JSON, e.g. {"query": "Claims"}')
    from atg.analysis import cli as analysis_cli

    analysis_cli.add_parsers(sub)
    args = parser.parse_args(argv)

    if args.cmd in ("mcp", "ask"):
        return _agent(args)
    if args.cmd in ("review", "authorise"):
        return analysis_cli.run(args)

    if args.cmd == "changes":
        return _changes(store.connect(args.db), args.head, args.base)
    if args.cmd == "serve":
        from atg.web.server import serve

        serve(args.db.resolve(), args.port, args.base_url)
        return 0

    roots = find_roots(args.export)
    if not roots:
        print(f"no export found under {args.export} (no META-INF/MANIFEST.MF)")
        return 2
    con = store.connect(args.db)
    failed = False
    for root in roots:
        try:
            sid, results = run_layers(con, root, max_paths=args.max_paths)
        except UnsupportedVersionError as e:
            print(f"SKIP {e}")
            continue
        print(f"\n== snapshot {sid}: {root.path} (Appian {root.appian_version})")
        for r in results:
            mark = "PASS" if r.ok else "FAIL"
            print(f"  {mark}  {r.name}: expected {r.expected}, got {r.actual}")
            for line in r.details:
                print(f"          {line}")
        failed |= not all(r.ok for r in results)
        _print_external(con, sid)
    return 1 if failed else 0


def _changes(con: sqlite3.Connection, head: int | None, base: int | None) -> int:
    from atg.web.changes_api import changes

    head = head or int(con.execute("SELECT MAX(id) FROM snapshots").fetchone()[0] or 0)
    r = changes(con, head, base)
    if "error" in r:
        print(r["error"])
        return 2
    print(f"Snapshot {r['head']} compared with {r['base']}")
    for c in r["changes"]:
        print(f"  {c['status']:8} {c['type']:13} {c['name']}")
    print(f"  {len(r['affected'])} objects affected through dependencies")
    for kind, counts in r["summary"].items():
        print(f"  {kind + 's':9} " + ", ".join(f"{n} {v}" for v, n in sorted(counts.items())))
    return 0


def _agent(args: argparse.Namespace) -> int:
    import json

    from atg.agent import atlas, mcp, tools

    if not args.db.exists():
        print(f"no map at {args.db}: run atg ingest first", file=sys.stderr)
        return 2
    con = store.connect(args.db)
    sid = args.snapshot or mcp.latest(con)
    if args.cmd == "mcp":
        mcp.serve(con, sid, base_url=args.base_url)
        return 0
    at = atlas.load(con, sid)
    at.memo["base_url"] = args.base_url
    out = tools.call(at, args.tool, json.loads(args.args))
    print(json.dumps(out, indent=1))
    return 1 if "error" in out else 0


def _print_external(con: sqlite3.Connection, sid: int) -> None:
    rows = con.execute(
        "SELECT kind, COUNT(DISTINCT target), SUM(occurrences) FROM refs "
        "WHERE snapshot_id = ? AND resolved = 0 GROUP BY kind ORDER BY 2 DESC",
        (sid,),
    ).fetchall()
    if rows:
        print("  external (points outside this export, not a failure):")
        for kind, targets, occ in rows:
            print(f"          {kind}: {targets} targets, {occ} uses")


if __name__ == "__main__":
    sys.exit(main())
