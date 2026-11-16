# Appian Test Generator

Reads an Appian **20+** export, builds a map of the app in SQLite, and (in later layers)
generates tests for it. Design and decisions: [DESIGN.md](DESIGN.md).

Code layout, where to change what, and conventions: see [CLAUDE.md](CLAUDE.md).

## Status

- **Layer 1, inventory and references: built.** Every object, reference and process node of
  the export goes into SQLite, proved by checks that count the raw files independently.
- **Layer 2, SAIL parser and decision points: built.** Lark grammar in `src/atg/sail/`; every
  expression must parse and print back identically. Checks: sources parsed, round trip,
  `if()` and `forEach` counts against the raw text.
- **Layer 3, process paths: built.** `src/atg/layers/path_engine.py`: one path per combination
  of gateway choices; AND splits run all branches; loops run 0, 1 and 2 times; paths whose
  choices contradict are dropped. Checks: every reachable node and every gateway option is on a
  path, every process has a path, none cut off at the 2,000-path limit.
- **Layer 4, features: built.** Entry points (site pages, record actions, web APIs) and
  everything each one reaches. A person approves them through an Excel sheet: dropdown
  decisions, blank never counts, edit needs a name, a changed feature needs re-approval.
- **Test design (offline): built.** Screens, test data, form fields by label, page paths and
  plain-English UAT scenarios per process path and screen; regression impact between imports.
- Running tests (Playwright) needs an Appian environment: not started.

## Appian versions

20.1 and up. Exports from 20.1 to 26.6 share one XML format ("Haul"), so one reader covers
them; versions differ only in which object and node types appear, listed in
`src/atg/read/known.py` (add one only after seeing it in a real export). Older exports are
refused, not guessed. The reader was checked against real exports from 20.1 to 26.6 during
development; the test suite uses a made-up export instead (below).

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

Nothing else is downloaded: no sample data, no fonts, no services. To try the tool without a
real export, write the made-up demo export (an "Expense Claims" app) and import it:

```bash
.venv/Scripts/python -m tests.demo out/expense-claims
```

## Use

Local web tool (import, live progress, results):

```bash
.venv/Scripts/atg serve --db map.db
```

Then open http://127.0.0.1:8777. Three views, picked in the top bar:

- **Tests** (home): every test on the left, filtered by kind (screens, processes, rules) or by
  feature. The home page shows the counts, the test users needed and the feature sign-off
  (download the Excel sheet, upload it filled in). Pick a test to see its **UAT scenario**
  (before you start, numbered steps, expected result, what the business must confirm; "Copy
  as text") and its **test data**. A process shows its paths and its diagram with the picked
  path highlighted. Screens include every interface a person opens (site pages, record views,
  start forms, user task forms, and ones nothing opens), because many never pass through a
  process.
- **App**: every object read-only, as in Appian Designer, grouped by type. A process shows its
  diagram (click a node for its properties); every page shows its code with clickable
  references, what it uses, what uses it, and "See its tests".
- **Changes**: compare with an earlier import of the same app: what changed, what that affects
  through dependencies, and which tests to rerun, add, retire or skip. Click a change for a
  line-by-line diff.

The top bar also has the snapshot picker, a **checks** chip (opens the health of the map: each
layer with its checks, decision points, how numbers moved since the previous import) and
**Import** (paste a folder or zip path, or drop a zip; earlier imports). With nothing imported
yet, the page asks for an export. Details open in a side panel on the right (Esc closes it).

What the test data covers: start inputs and their fields; the conditions the data must meet,
in plain words ("doc is filled in", "status = 2"); what people fill in at each task, by field
label ("decision: “Decision” (radio buttons)", "click the button “Send”"); for each record
type the table its rows go in, whether it is synced, its related records and the fields Appian
calculates; buttons and what they do; file upload fields; outside systems; values worth trying
(empty and filled in, 0/1/many items, around compared values) and test inputs developers saved
in Appian. Steps carry paths under the Appian base URL built from the export's urlStubs
(`src/atg/testgen/urls.py`): site pages `/suite/sites/<site>/page/<page>`, record lists
`/suite/tempo/records/type/<stub>/view/all`, tasks `/suite/tempo/tasks` (Appian's defaults;
check them on your server).

Names and labels are shown exactly as they are in the export.

Regression from the command line: `atg changes --db map.db` (latest snapshot vs the previous
import of the same app; `--base` / `--head` pick others). To try it, import the demo export,
then its next release (`python -m tests.demo out/expense-claims-next --next`: three edits).

How impact spreads (`src/atg/regression/impact.py`, verdicts in `src/atg/regression/verdicts.py`): an object is
affected when it uses a changed or removed one, transitively. Two kinds of reference are not
followed, because they are not data dependencies: a record type's own views and actions, and
anything that merely starts a process (sub-processes are tested on their own). A test path is
rerun when it passes through a changed node or a node that uses something affected.

Command line only:

```bash
.venv/Scripts/atg ingest path/to/export-or-zip --db map.db
```

Every ingest is a new snapshot. It prints each Layer 1 check (PASS/FAIL) and what points
outside the export. Exit code 1 if any check fails.

## Agent tools (MCP)

An AI agent exploring the running app (logged in as one test user at a time) can use the map
as a helping hand: `atg mcp --db map.db` serves it as an MCP server over stdio. Register it in
an MCP client, e.g. `claude mcp add appian-map -- atg mcp --db /path/to/map.db`.

| Tool | What it gives |
|---|---|
| `overview` | object counts, the doors (ways in) by kind, groups. Call first |
| `doors` | every site page, record action, record view, user task and web API, with URL and gates |
| `find` | from what the agent sees (a URL, a title, text on a screen, a name) to ids |
| `card` | one object or door: uses, used by, doors that reach it, gates, what it changes, decisions, gaps |
| `neighbours` | links one step out |
| `process` | tasks and who gets them, and test paths covering every gateway option once, with what each changes |
| `who` / `visible_to` | the gates on the way to something; everything one group can reach |
| `record` / `coverage` | the agent's findings per user (seen, matches, differs, hidden, refused, broken) and what is left |
| `census` / `actors` / `access_check` / `lifecycle` | what the map holds and cannot see; every kind of actor; doors shown to people who may not use them; record types against create, read, update, delete |
| `resume` / `next_item` / `submit` | the work queue: code picks the next door or object, the agent answers fixed questions, every claim is checked against the map before it is kept |
| `drafts` / `draft` / `use_cases` / `test_ideas` / `progress` | feature proposals, use cases and test ideas for approved features, and the honest counts |

### Working through a large app

The agent starts every session with `resume`, then repeats `next_item` and `submit`. Code, not
the model, picks the order: doors that reach the most unread objects first, then doors that
write, then rare triggers (timers, APIs, messages). Each door comes with six fixed questions
(what it starts or writes, which records and statuses, who gets tasks, what guards it, which
doors do the same, what leaves the app). A claim is refused unless every object it cites exists,
every quote matches the stored source and every path follows real links; the agent may only
claim "stated", "inferred" or "statically supported". Work is kept in `<map>.analysis.db`, next
to the map, so a re-import never touches it and unchanged work is reused.

Feature drafts are built by fixed rules (doors that open the same thing, or act on one record
type and reach mostly the same objects; tasks join the draft that starts their process) and
say why and what speaks against them. People decide in the **Analysis** view of the web tool
or with `atg review` (merge, split, move, rename, exclude, shared, approve, answer); every
decision is previewed first and replayed on every later build. A draft can also be
**auto-accepted** without a person when six countable checks pass: one user type and at most
one main record type, no doubts, every door assessed and every core object described, two
separate challenge passes that re-checked it and said it holds, nothing open or blocked, and
at most five doors. Auto-accepted is counted apart from people's approvals, a person can still
reject it, and any change underneath drops it back to draft. An approval keeps the inputs it
was given on and shows as stale when they change. Use cases and test ideas exist only for
approved features; their expected results say where they come from, and business results
always need a person. Runtime checks need `atg authorise` for the environment, and never raise
a static progress measure. `python -m scripts.evaluate_grouping` scores the drafts against a
grouping people made on their own.

Gates are read from page, record action and record view visibility and from screen SAIL:
group checks (also through constants that hold a group), the user's own data
(`loggedInUser()`), and profile fields. Each says how sure it is (read, resolved, unresolved).
Gaps say what the map cannot tell (references outside the export, logic that did not parse,
processes chosen at run time) so the agent explores those by hand. `atg ask <tool> '<json>'`
calls one tool from the shell.

## Layer 1 checks

| Check | Compares |
|---|---|
| data files → object or unknown | every `.xml`/`.xsd` became an object or was reported |
| objects per Haul type | raw root-tag count vs SQL |
| process nodes / connections / gateway rules / defaults | raw text counts vs SQL |
| canonical `#"` refs | raw `#"` count vs stored references |
| UUID sweep | every UUID in the raw text got exactly one classification |
| unknowns | must be 0 — new tags, node types or files fail loudly |

`tests/test_break_it.py` plants a bug for each check and expects it to fail.

## Golden sample (needs you)

Open `tests/golden/demo-review.md`. If the 5 objects match their code, set `approved_by` and
`approved_on` in `tests/golden/demo.json`. From then on `test_golden.py` freezes them
(regenerate both with `python -m scripts.make_golden`).

## Tests

All tests run on a made-up export written by `tests/demo/` (`spec.py` holds the app: objects,
SAIL, process flows; no real company's data). Frozen numbers in the tests are counted on it;
a change in them must be explained in that test.

## Quality

```bash
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check . && .venv/Scripts/mypy && .venv/Scripts/python -m pytest -q
```
