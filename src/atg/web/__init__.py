"""Local web tool on 127.0.0.1: an HTTP server, a background import queue, one module per view.

server       routing: /api/snapshots/<id>/<view> -> a function below; static files
jobs         imports running in the background
api          overview: snapshots, checks, progress, dependencies, processes
designer_api Designer pages: an object or process node, code in Designer form
paths_api    test paths, decision points, test users
features_api one feature and its members, entries pointing outside the export
changes_api  regression view: changes, impact, verdicts, line diffs
tests_api    Tests tab: every test (screens, process paths, rules), its data and UAT scenario
static/      the UI: index.html; core.js (state, fetch, helpers), app.js (shell, three views),
             tests.js + testpage.js + testdata.js (Tests), browse.js (App), changes.js,
             panel.js (side panel), health.js, importer.js, diagram.js, nodeprops.js, code.js
"""
