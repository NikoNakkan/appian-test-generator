"""Layer 1: read an Appian export (folder or zip) into a Snapshot of objects and references.

source    find export roots (META-INF/MANIFEST.MF) and their files; Appian version
select    pick the reader for that version (20+ only)
haul      read one "Haul" XML file into an AppObject (+ unknowns, + UUID scan)
known     what the reader recognises: Haul roots, content subtypes, process node types
details   what Designer shows per object and process node (inputs, settings, forms)
records   record type facts (fields, relationships, data source, actions), saved rule tests
process   process models: nodes, flows, gateways
entry     entry points: site pages, record actions
scan      every UUID in a file, with where it appears
link      turn scanned UUIDs into references between objects
ingest    all of the above for one export root -> Snapshot
hashing   content hash of an XML file, for change detection
xmlutil   small ElementTree helpers (namespaces, child text, UUID pattern)
"""
