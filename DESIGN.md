# Appian Test Generator — Design

Status: layers 1 to 4 and offline test design are built; running tests needs an Appian
environment. See README.md for what exists now.

## Goal

Read an Appian application export, build a complete map of the app, and generate
tests that cover every feasible branch and path, feature by feature. Tests run on a
dev server. A human approves expected results. Built **layer by layer**: a layer is
only "done" when its own checks pass, so progress is real, not a feeling.

## Principles

1. **Each layer is proven by automatic checks against the raw export**, plus a small
   golden sample approved once by a human. Never "it looked right".
2. **Every check must be able to fail.** Break the input on purpose; the check must catch it.
3. **Stable core model, modular version readers.** A new reader is written only when a
   real sample proves the format differs. Unknown tags, node types or SAIL functions
   go to an "unknown" report and fail the run loudly.
4. **No AI in layers 1–3.** AI sits on top of solid code, behind one swappable module
   (`ai_client.py`), so the provider can change in one file.
5. **Progress ratchet.** Every run is compared with the last; key numbers may only stay
   the same or go up. A drop is flagged with its reason.
6. Python, type hints, mypy/pyright, ruff, files ≤250 lines. SQLite for the map.
7. Self-contained: no outside code copied, no outside services or downloads at run time.

## Export format facts (from real exports)

- Export = ZIP of folders: `application/`, `content/`, `processModel/`, `recordType/`,
  `datatype/`, `group/`, `connectedSystem/`, `site/`, `META-INF/`.
- Each file is one object wrapped in `<xxxHaul>`, identified by UUID.
- Version is in `META-INF/MANIFEST.MF` → `Appian-Version: 25.4.350.0`.
- SAIL is stored in **canonical form**:
  - own objects: `#"_a-0000ec54-..._8021479"(...)` (UUID, not `rule!Name`)
  - platform functions: `#"SYSTEM_SYSRULES_textField"(...)`
  - record fields: `#"urn:appian:record-field:v1:<recordUuid>/<fieldUuid>"`
  - types: `'type!{namespace}Name'`
- Rule inputs: `<namedTypedValue>` with `<type><name>`.
- Rule test cases live in the export as `RuleTestConfig?list`
  (`ruleInputTestConfigs` + `assertions`) → tests can be **written back** in Appian's own format.
- Process model: `processModelHaul/process_model_port/pm` → `pvs`, `nodes`, `lanes`.
  - node type: `node/ac/local-id` (`core.0` start, `core.1` end, `core.2` AND,
    `core.4` XOR, `core.5` complex, `core.7` wait event, `internal.38` subprocess,
    `internal.16` script, `internal.17` user task, …)
  - flows: `node/connections/connection/to` (target node guiId)
  - XOR: acp `rules` → list of (`expression`, `node` target, `label`) + acp `defaultNode`

### What a mid-size real app looks like (Appian 25.4)

Around 400 objects: 70 interfaces, 66 rules, 52 constants, 11 integrations, 8 record types,
84 process models (about 1,300 nodes, 230 XOR gateways, 380 sub-process calls, 50 user tasks,
30 wait events). Hundreds of saved test inputs but **no expected results**. A quarter of rule
references point **outside** the export, to shared library apps.

The reader was checked on real exports from 20.1 to 26.6. They are not part of this
repository; the tests use a made-up export (`tests/demo/`).

## Layers

Each layer reads only the previous layer's output (SQL), never jumps back to raw XML
except Layer 1 (and Layer 2 for SAIL text it stores).

### Layer 1 — Inventory + references → SQL (code only)

- Every object, every reference (SAIL canonical refs + structural XML refs), every
  process node and connection.
- **Snapshots:** every row has a `snapshot_id`; one per export. Object content is hashed
  (after normalising volatile parts such as `versionUuid`, history).
- Platform version and shared apps are recorded per snapshot.

**Done when:**
- Count match: raw text counts (`<connection>`, objects per type, `#"_a-…"` refs) equal SQL counts exactly.
- UUID sweep: every UUID in the raw XML is mapped, marked external, or on a known-noise list.
- Golden sample: ~5 objects checked fully by hand once, frozen as tests.
- Break-it test: remove one reference from a copy → a check fails.
- Runs on exports from every supported version; the unknown report is empty.

### Layer 2 — SAIL parser → branches per rule (code only, Lark)

- Parse canonical SAIL into a tree; extract branches (`if`, `and/or`, `a!match`,
  `choose`, null checks, `a!forEach`) and the values they compare against.
- Unparseable rule → marked **unparsed**, 0 tests, listed in the report; run continues.

**Done when:** 100% of rules + interfaces parse, and **round-trip** (parse → print →
compare, whitespace ignored) matches on all of them.

### Layer 3 — Process graph → paths (code only)

- Build graph from nodes + connections; gateway conditions from Layer 2.
- **All feasible paths per process.** Subprocesses tested **separately** (parent test
  only checks the call and its inputs). Loops: 0, 1, max+1 passes.
- One data set per path + boundary values for numeric conditions.
- Drop impossible paths (contradictory conditions).
- Output also lists **test users needed** per group (2 per role).

Real-app worst case seen: about 2,400 paths in total, largest single process about 1,000.

### Layer 4 — Features (code + AI + human)

- Code finds entry points (site pages, record actions, process starts, web APIs) and
  everything reachable from each.
- AI groups and names them in business words; every feature must point to real
  entry-point UUIDs or it is rejected.
- Human approves the list once. New entry points in later snapshots are proposed one by one.
- Shared rules are tested once at rule level; feature tests cover the flow.

### Layer 5 — Test design + running

- **Rules:** generated as Appian test cases (`RuleTestConfig`), run via Start Rule Tests + Web API.
- **Processes:** started via Web API; human tasks completed as dev test users.
- **Screens:** first run is **agentic** (AI explores and records); saved as a plain
  Playwright spec; later runs are the spec only, no AI.
- Rerun rules by hash: export objects + platform version + shared apps.
  Failure with **unchanged** hashes → AI repair → human approves.
- Test data: every record tagged `TEST_<runId>`; a sweeper deletes leftovers and cancels
  stuck processes before each run; tests never share data.
- Full run weekly; per-export runs only for changed hashes and their dependents.

### Layer 6 — Expected results (AI proposes, human approves)

- Approved results become the baseline, tied to `snapshot_id` + object hash.
  Object changes → "needs re-approval", never silently reused.
- Approval via **Excel** for now (`openpyxl`, one module, swappable for a web page later):
  - each row has item ID + hash; stale rows rejected on import
  - dropdown `approved / edit / rejected`; anything else rejected; blank ≠ approved
  - edited values type-checked; approver name + date recorded

## Progress measures (ratchet, no pass mark)

- Coverage: % of branches/paths with an approved test, per feature.
- Acceptance rate: AI proposals approved without edit.
- Recording success: % of agentic recordings that replay as plain Playwright.
- Flake rate: pass/fail changes with no hash change (target ≈ 0).
- Frozen exam: 3–5 features with fully approved tests; rerun on every prompt/model change.

## Security

- Test users only, never real accounts. Passwords in environment variables or a vault, never in
  code, SQL or tests.
- Mask secrets (tokens, passwords, keys) before anything is written or sent to AI.

## Open risks

1. Whether a cloud AI may see the app's code — **to be approved by the owner** before any AI step.
2. Outside systems on dev — real test versions or fakes — **unknown**. If fakes are
   allowed, point Connected Systems at a `fake_services/` server; otherwise error-path
   tests are marked "can't run here".
3. The target app's Appian version — check first: Layer 1 + the unknown report only.
4. Shared library apps must be exported too, or ~25% of references stay external.
5. Human tasks, wait events and timers make process tests slow; may need time faking.

## First step on a new app

Import its export (and its shared library apps), check Layer 1 and the unknown report.
