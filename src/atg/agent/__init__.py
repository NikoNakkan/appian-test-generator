"""What an exploring agent reads: the map as cards it can look up, follow and tick off.

atlas.py    the map loaded once: objects, links both ways, constants resolved
gates.py    who may see or do something (groups, own data, profile), through constants
effects.py  what a process node or button changes (records, tasks, processes, integrations)
process.py  a process as a diagram summary plus paths that cover every gateway option
doors.py    the ways a user gets in (pages, record actions, record views) with their gates
cards.py    one card per object: uses, used by, gates, effects, decisions, gaps
find.py     from what the agent sees (URL, text) to cards
who.py      who can reach what, and the reverse
ledger.py   the agent's findings and what is still unseen
tools.py    the tools (name, description, parameters, function)
mcp.py      the tools over MCP (stdio), for `atg mcp`
"""
