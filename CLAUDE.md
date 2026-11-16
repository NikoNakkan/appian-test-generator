# Appian Test Generator: code map

Reads an Appian 20+ export (folder or zip), builds a map of the app in SQLite layer by layer
(each layer proved by automatic checks), then works out what every test needs: test data,
screens, form fields, UAT scenarios. A person approves expected results; Playwright specs come
after. Read `README.md` for how to use it and `DESIGN.md` for why it is built this way.

## Data flow

```
export folder/zip
  └─ read/        Layer 1: Haul XML files -> objects, references, process nodes  (model.Snapshot)
  └─ store.py     save the Snapshot into the map (SQLite, one snapshot per import)
  └─ layers/      Layer 2 SAIL decision points · Layer 3 test paths · Layer 4 features
                  checks/ proves each layer against counts taken from the raw files
  └─ mapdb.py     read helpers over the map (names, details, settings, SAIL definitions)
       ├─ testgen/     test data, screens, form fields, UAT scenarios, page URLs
       ├─ regression/  what changed between two imports, which tests rerun
       ├─ approvals.py feature approval through an Excel sheet
       ├─ agent/       the map as tools for an exploring AI agent (cards, find, who, doors,
       │               actors, reach, lifecycle), served over MCP by `atg mcp`
       ├─ analysis/    kept apart in <map>.analysis.db: work queue, verified agent claims,
       │               feature drafts, people's decisions, use cases, test ideas, progress
       └─ web/         local web tool: server + one *_api module per view + static/ UI
  sail/  the SAIL language (parser, printer, Designer form, phrases, buttons, fields),
         used by layers/, testgen/ and web/
```

Every package's `__init__.py` docstring lists its modules in one line each: start there.

## Where to change what

| Task | Start in |
|---|---|
| Support a new object type or process node | `read/known.py`, then `read/haul.py` / `read/details.py` |
| Read a new fact from an object's XML | `read/details.py` (generic), `read/records.py` (record types, saved tests) |
| SAIL grammar or parsing | `sail/ast.py` (+ `printer.py` must round-trip) |
| How code is shown (UUIDs -> names) | `sail/display.py` |
| Conditions in plain English | `sail/explain.py` |
| Buttons / form fields on screens | `sail/actions.py`, `sail/fields.py`, `testgen/forms.py` |
| Test paths through processes | `layers/path_engine.py` (pure), `layers/layer3_paths.py` (store) |
| Features and reach | `layers/feature_engine.py` |
| Test data per path / rule | `testgen/testdata.py` |
| Screens and how people reach them | `testgen/screens.py` |
| UAT scenario wording | `testgen/scenarios.py`, `testgen/sentences.py` |
| Page URLs | `testgen/urls.py` |
| Regression impact / verdicts | `regression/impact.py`, `regression/verdicts.py` |
| A new web view | `web/<view>_api.py` + route in `web/server.py` + `web/static/<view>.js` |
| Map schema | `store.py` (tables below) |
| Test fixture (made-up export) | `tests/demo/spec.py` (objects), `xml.py`, `process.py` |
| Who may call the web tool | `web/guard.py` |
| A tool for the exploring agent | `agent/tools.py` (registry) + a module in `agent/` |
| Gates (who may see/do what) | `agent/gates.py` (SAIL), `agent/doors.py` (pages, actions, views, tasks) |
| What a process or button changes | `agent/effects.py`, `agent/cards.py` |
| What starts a process (timer, message, API) | `agent/triggers.py` |
| Permission (role maps) / shown vs allowed | `read/security.py` (reading), `agent/security.py` |
| Which item the agent works on next | `analysis/queue.py` (selection is code, never the model) |
| What a claim must prove before it is stored | `analysis/verify.py` |
| How doors are grouped into feature drafts | `analysis/drafts.py`; people's overrides `analysis/review.py` |
| When a draft is auto-accepted | `analysis/certainty.py` (countable checks only, never model confidence) |
| What a draft reviewer is given / how a review is checked | `analysis/brief.py`, `analysis/reviews.py` |
| Instructions for the lead and reviewer agents | `agent/playbook.py` (served by the playbook tool) |
| Progress measures | `analysis/progress.py` (one item type and denominator each; no blended %) |
| Analysis web view | `web/analysis_api.py` + `web/static/analysis.js` |

## The map (SQLite)

Every row has `snapshot_id`. Main tables: `objects` (uuid, type, name, path, content_hash),
`refs` (source -> target), `object_details` / `node_details` (JSON, what Designer shows),
`nodes` / `flows` (process models), `expressions` (SAIL text per owner), `branches` (decision
points), `paths` / `path_stats`, `entry_points`, `features` / `feature_members`,
`feature_approvals`, `check_results`. Canonical names in SAIL are UUIDs:
`#"_a-...uuid"` (object), `#"SYSTEM_SYSRULES_x"` (built-in a!x), `urn:appian:record-field:v1:<rt>/<field>`.

## Conventions

- Python 3.12, `from __future__ import annotations`, fully typed (`mypy --strict`), ruff
  (line length 100). Files stay at or under 250 lines: split by responsibility before that.
- Module docstring first: what it does and the XML or data shape it reads.
- Read the map only through `mapdb.py` (the agent package through its `Atlas`); write it only
  in `store.py`, the layer runners and `agent/ledger.py` (runtime findings).
- Three layers never mix: imported facts (the map), agent claims (`analysis/`, verified, each
  with a level: stated, inferred, statically supported), people's decisions (append-only).
  The agent has no tool that approves, merges, splits or authorises: only people decide.
- Runtime findings never raise a static progress measure.
- `web/` may import everything; nothing outside `web/` imports `web/` (except `cli.py`).
- No private (`_name`) imports across modules: make a helper public where it belongs.
- Names and labels are shown exactly as in the export (often Spanish); UI text is English.
- Exports are untrusted data: never run code from inside one; zips unpack through
  `read/source.py`, which refuses entries outside their folder and oversized archives.
- Self-contained: no network calls, no downloads, nothing loaded from outside in the UI
  (`web/guard.py` sets a strict Content Security Policy and refuses foreign Host/Origin).
- Tests use only the made-up export in `tests/demo/` (`spec.py`); never add real app data.

## Commands

```bash
.venv/Scripts/ruff check src tests scripts && .venv/Scripts/ruff format src tests scripts
.venv/Scripts/mypy src tests scripts
.venv/Scripts/python -m pytest                   # all tests, about 20 seconds
.venv/Scripts/python -m tests.demo out/demo       # write the demo export (--next: 3 edits)
.venv/Scripts/atg ingest out/demo --db map.db
.venv/Scripts/atg serve --db map.db --port 8777
.venv/Scripts/atg ask --db map.db find '{"query": "Claims"}'   # one agent tool, printed
.venv/Scripts/atg mcp --db map.db                 # the agent tools as an MCP server (stdio)
.venv/Scripts/atg review approve <draft key> --by NAME --preview   # a person's decision
.venv/Scripts/atg authorise --env test --mode observe --by NAME    # allow runtime checks
.venv/Scripts/python -m scripts.evaluate_grouping --db map.db --reference ref.json
```

After changing anything under `read/`, re-import (`atg ingest`) so `map.db` has the new facts.
`tests/test_export.py`, `test_layer*.py` and `test_regression.py` freeze numbers counted on
the demo export: a change that alters them must say why in that test's docstring.
