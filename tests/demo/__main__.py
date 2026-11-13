"""python -m tests.demo <folder> [--next]: write the demo export (or its next release) to try
the tool: import the folder in the web tool, or with `atg ingest <folder>`."""

from __future__ import annotations

import sys
from pathlib import Path

from tests.demo import build, build_next

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--next"]
    if len(args) != 1:
        sys.exit("usage: python -m tests.demo <folder> [--next]")
    folder = (build_next if "--next" in sys.argv else build)(Path(args[0]))
    print(f"wrote {folder}")
