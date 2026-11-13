"""Write tests/golden/demo.json (unapproved) and demo-review.md for a human to check once.

Run from the project root: python -m scripts.make_golden
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from atg.golden import DEMO_GOLDEN, extract, review_markdown
from atg.read.ingest import read_snapshot
from atg.read.source import find_roots

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "golden"
_SAIL_RE = re.compile(r"<(definition|a:expr|expr)>(.*?)</\1>", re.DOTALL)


def _excerpt(path: Path, limit: int = 4000) -> str:
    text = path.read_text(encoding="utf-8")
    sail = [m.group(2).strip() for m in _SAIL_RE.finditer(text) if m.group(2).strip()]
    body = "\n---\n".join(sail) if sail else text
    body = body.replace("<![CDATA[", "").replace("]]>", "")
    return body[:limit] + ("\n... (cut)" if len(body) > limit else "")


def main() -> None:
    from tests.demo import build

    (root,) = find_roots(build(Path(tempfile.mkdtemp()) / "Expense Claims"))
    snap = read_snapshot(root)
    golden = extract(snap, DEMO_GOLDEN)
    excerpts = {u: _excerpt(root.path / g["path"]) for u, g in golden.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {"approved_by": None, "approved_on": None, "objects": golden}
    (OUT / "demo.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "demo-review.md").write_text(review_markdown(golden, excerpts), encoding="utf-8")
    print(f"wrote {OUT / 'demo.json'} and demo-review.md")


if __name__ == "__main__":
    main()
