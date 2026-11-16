"""Compare the feature drafts with a grouping people made on their own.

python -m scripts.evaluate_grouping --db map.db --reference reference.json
reference.json: {"feature name": ["door id", ...], ...} (door ids as the doors tool shows them)
Run it on a slice people decomposed before seeing any tool output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atg import store
from atg.agent import atlas, mcp
from atg.analysis import drafts, evaluate
from atg.analysis.store import open_for


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path("map.db"))
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--snapshot", type=int)
    args = p.parse_args()
    con = store.connect(args.db)
    at = atlas.load(con, args.snapshot or mcp.latest(con))
    truth = {k: set(v) for k, v in json.loads(args.reference.read_text(encoding="utf-8")).items()}
    built = drafts.build(at)
    found = {d["key"]: {x["id"] for x in d["doors"]} for d in built}
    auto = {d["key"] for d in built if d["status"] == "auto-accepted"}
    decisions = open_for(at).execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    print(json.dumps(evaluate.compare(found, truth, decisions, auto), indent=1))


if __name__ == "__main__":
    main()
