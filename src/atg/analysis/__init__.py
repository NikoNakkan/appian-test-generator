"""Analysis kept apart from the imported map: what the agent did, what it claimed, what people
decided. Lives in its own file next to the map (<map>.analysis.db), so a re-import never
touches it, and every row says which snapshot it was made on.

  store.py      the analysis file: schema, idempotency keys, input hashes
  queue.py      work items: seeding, which item comes next, leases, resume after a reset
  verify.py     checks every agent claim against the map before it is stored
  ledger.py     submit (claims + reads + status, in one transaction), questions for a person
  drafts.py     feature drafts by fixed rules, shaped by people's decisions, with doubts
  labels.py     one accounting label per object (core, shared, supporting, unreached, ...)
  review.py     people's decisions as an append-only list, replayed on every build
  decide.py     checks a decision, previews what it would change, records it
  evaluate.py   drafts against a people-made grouping (extended B-cubed), run stability
  cli.py        atg review, atg authorise
  usecases.py   use cases for approved features, with nearest negatives
  testideas.py  coverage items and test ideas for approved use cases
  progress.py   the ten progress measures, each with numerator, denominator and rule
  authorise.py  which environments may be used for runtime checks
"""
