"""The agent tools over MCP: JSON-RPC 2.0 on stdin/stdout, one message per line.

Run `atg mcp --db map.db` as an MCP server (stdio). Read-only except record(), which adds a row
to the findings table. Uses the latest snapshot unless --snapshot is given.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, TextIO

from atg.agent import atlas as atlas_mod
from atg.agent import tools

PROTOCOL = "2025-06-18"


def latest(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COALESCE(MAX(id), 0) FROM snapshots").fetchone()[0])


def handle(at: atlas_mod.Atlas, msg: dict[str, Any]) -> dict[str, Any] | None:
    method, mid = msg.get("method", ""), msg.get("id")
    if mid is None:
        return None  # a notification (e.g. notifications/initialized)
    if method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "appian-map", "version": "0.1.0"},
            "instructions": (tools.__doc__ or "").split("\n\n")[1],
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": t.name, "description": t.description, "inputSchema": tools.schema(t)}
                for t in tools.TOOLS
            ]
        }
    elif method == "tools/call":
        p = msg.get("params", {})
        out = tools.call(at, p.get("name", ""), p.get("arguments") or {})
        text = atlas_mod.dumps(out)
        result = {"content": [{"type": "text", "text": text}], "isError": "error" in out}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": method}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(
    con: sqlite3.Connection,
    sid: int,
    inp: TextIO = sys.stdin,
    out: TextIO = sys.stdout,
    base_url: str = "",
) -> None:
    at = atlas_mod.load(con, sid)
    at.memo["base_url"] = base_url
    for stream in (inp, out):  # Windows consoles default to a local code page
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    for line in inp:
        if not line.strip():
            continue
        try:
            reply = handle(at, json.loads(line))
        except Exception as e:  # one bad call must not stop the server
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()
