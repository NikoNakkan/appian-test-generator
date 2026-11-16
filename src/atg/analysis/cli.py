"""atg review and atg authorise: the decisions only people make.

atg review <kind> <target> --by NAME [--reason ...] [--payload JSON] [--preview]
atg authorise --env NAME --mode observe|act --by NAME [--scope ...] [--days N]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atg import store
from atg.agent import atlas, mcp
from atg.analysis import authorise, decide, review


def add_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    rv = sub.add_parser("review", help="record a person's decision on drafts, use cases, tests")
    rv.add_argument("kind", choices=sorted(review.KINDS))
    rv.add_argument("target", help="door id, draft key, object, use case, test or question id")
    rv.add_argument("--by", required=True, help="who decides")
    rv.add_argument("--reason", default="")
    rv.add_argument("--payload", default="{}", help='JSON, e.g. {"with": "<door id>"}')
    rv.add_argument("--preview", action="store_true", help="show what would change, keep nothing")
    au = sub.add_parser("authorise", help="allow runtime checks in one environment")
    au.add_argument("--env", required=True)
    au.add_argument("--mode", required=True, choices=authorise.MODES)
    au.add_argument("--by", required=True)
    au.add_argument("--scope", default="all")
    au.add_argument("--days", type=int, default=7)
    for p in (rv, au):
        p.add_argument("--db", type=Path, default=Path("map.db"))
        p.add_argument("--snapshot", type=int, help="default: the latest import")


def run(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"no map at {args.db}: run atg ingest first")
        return 2
    con = store.connect(args.db)
    at = atlas.load(con, args.snapshot or mcp.latest(con))
    if args.cmd == "authorise":
        out = authorise.grant(at, args.env, args.scope, args.mode, args.by, args.days)
    else:
        out = decide.decide(
            at,
            args.kind,
            args.target,
            args.by,
            args.reason,
            json.loads(args.payload),
            preview=args.preview,
        )
    print(json.dumps(out, indent=1))
    return 1 if "error" in out else 0
