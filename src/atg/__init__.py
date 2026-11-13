"""Appian test generator: read an Appian export, map the app, generate tests layer by layer.

Data flow (each step writes to the SQLite map; see CLAUDE.md at the project root):
  read/       Layer 1  export files -> objects, references, process nodes (model.Snapshot)
  store       save a Snapshot into the map (schema + inserts)
  layers/     Layers 2-4 SAIL decision points, test paths, features; checks/ prove each layer
  mapdb       read helpers over the map, shared by everything below
  testgen/    test data, screens, form fields, UAT scenarios, page URLs
  regression/ what changed between two imports and which tests rerun
  approvals   feature approval through an Excel sheet
  web/        local web tool (HTTP server + one *_api module per view + static UI)
  sail/       the SAIL language: parser, printer, Designer-form display, phrases, actions
"""
