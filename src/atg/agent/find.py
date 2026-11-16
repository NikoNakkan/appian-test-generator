"""From what the agent sees to the map: a URL, a page title, a button or field label, a name.

Screens show text that is often built at run time (translations, rules), so a label may not be
found; the URL and the page or action titles are the surest anchors.
"""

from __future__ import annotations

import re
from typing import Any

from atg.agent import doors
from atg.agent.atlas import Atlas

_LITERAL = re.compile(r'"([^"\\#\n]{2,80})"')
_RECORD_URL = re.compile(r"records/(?:type|item)/([^/?#]+)")
_SITE_URL = re.compile(r"sites/([^/?#]+)(?:/page/([^/?#]+))?")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _score(query: str, text: str) -> int:
    q, t = _norm(query), _norm(text)
    if not q or not t:
        return 0
    if q == t:
        return 4
    if f" {q} " in f" {t} " or (len(t) > 3 and f" {t} " in f" {q} "):
        return 2
    words = set(q.split()) & set(t.split())
    return 1 if words and len(words) >= max(1, len(q.split()) // 2) else 0


def find(atlas: Atlas, query: str, kind: str = "", limit: int = 10) -> dict[str, Any]:
    if "/" in query:
        hits = _by_url(atlas, query)
        if hits:
            return {"query": query, "matched_by": "url", "results": hits[:limit]}
    found: dict[str, tuple[int, str, dict[str, Any]]] = {}

    def offer(key: str, score: int, how: str, ref: dict[str, Any]) -> None:
        wanted = kind in {"", ref.get("type"), ref.get("kind")}
        if score and wanted and (key not in found or found[key][0] < score):
            found[key] = (score, how, ref)

    for d in doors.doors(atlas):
        offer(d["id"], _score(query, d["name"]) + 1, d["kind"] + " title", _short(d))
    for uuid, (t, name) in atlas.objects.items():
        offer(uuid, _score(query, name), "name", atlas.ref(uuid))
        desc = atlas.det(uuid).get("description", "") if t in _DESCRIBED else ""
        if desc:
            offer(uuid, _score(query, desc) // 2, "description", atlas.ref(uuid))
        if t == "interface":
            best = max((_score(query, s) for s in _LITERAL.findall(atlas.text(uuid))), default=0)
            offer(uuid, best, "text on the screen", atlas.ref(uuid))
    ranked = sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return {
        "query": query,
        "results": [{**ref, "matched_by": how} for _, (s, how, ref) in ranked[:limit] if s > 1],
    }


_DESCRIBED = frozenset({"interface", "rule", "processModel", "recordType", "constant", "site"})


def _short(d: dict[str, Any]) -> dict[str, Any]:
    return {"id": d["id"], "type": "door", "kind": d["kind"], "name": d["name"], "url": d["url"]}


def _by_url(atlas: Atlas, url: str) -> list[dict[str, Any]]:
    all_doors = doors.doors(atlas)
    out = [_short(d) for d in all_doors if d["url"] and d["url"].split(" ")[0] in url]
    if "tasks" in url and not out:
        out = [_short(d) for d in all_doors if d["kind"] == "user task"]
    if m := _RECORD_URL.search(url):
        stub = m.group(1)
        out += [_short(d) for d in all_doors if f"/type/{stub}/" in d["url"]]
    elif m := _SITE_URL.search(url):
        site, page = m.groups()
        out += [
            _short(d)
            for d in all_doors
            if f"/sites/{site}/" in d["url"] and (not page or d["url"].endswith(f"/page/{page}"))
        ]
    return list({d["id"]: d for d in out}.values())
