"""What an exploring agent reads: the map as cards it can look up, follow and tick off.

atlas.py    the map loaded once: objects, links both ways, constants resolved
census.py   what the map holds and cannot see; what exports never contain
triggers.py what starts each process (person, API, timer, message, another process)
security.py permission from role maps; doors whose visibility and permission disagree
states.py   record states a door or condition depends on (status = "Approved")
actors.py   the kinds of actor the export shows, and their doors
reach.py    what each door reaches, fan-in, shared helpers
lifecycle.py record types against create, read, update, delete and statuses set
gates.py    who may see or do something (groups, own data, profile), through constants
effects.py  what a process node or button changes (records, tasks, processes, integrations)
process.py  a process as a diagram summary plus paths that cover every gateway option
route.py    how to get to a door in the running app: log in as, address, clicks, what first
doors.py    the ways a user gets in (pages, record actions, record views) with their gates
cards.py    one card per object: uses, used by, gates, effects, decisions, gaps
find.py     from what the agent sees (URL, text) to cards
who.py      who can reach what, and the reverse
ledger.py   the agent's findings and what is still unseen
tools.py    the tools (name, description, parameters, function)
worktools.py tools for working through the app: queue, drafts, use cases, progress
playbook.py how agents review feature drafts: a lead hands out drafts, one reviewer each
mcp.py      the tools over MCP (stdio), for `atg mcp`
"""
