# 1.3.0.dev8 source-scope outcome integration

## Input and reconciliation

The supplied `JEV_Selection_Checkpoint_6a271478.zip` has SHA-256
`6671e0b4f005a66b5132f2c1d566542f182701f4dd47ea9c0b31eab0ab1cc66d`.
Its 80 payload files matched `MANIFEST.sha256`, and the archive had no unsafe
paths or case collisions. The packet was a partial dev6 export, not a complete
repository checkout or merged release. It expressly identified dev7 PR #21 as
overlapping work and warned against applying its additive patch unchanged.

The integration preserves the merged dev7 selector, planner and tests. It adds
the packet's whole-source scope review as a separate repository placement
stage, renames the colliding test module, removes its obsolete dev6 optimizer
blob assertion, routes the stage through the central CLI, and registers its
contracts, examples, docs and CI. The qualification-only partial-wheel and
mutation scripts from the packet are not shipped as release tooling.

## Behavior and limits

The new context reconstructs current discovery, nomination, inventory and
semantic review from source. A bounded negative outcome requires complete
within-policy coverage and a separate all-negative review of every enumerated
file and seam. Empty inventory, unsupported shapes, excluded source and missing
review rows remain distinct. The result is a review judgment within its
enumerated policy scope, not a universal proof of absence.

Set selection is review-only and does not generate a bundle. The existing dev7
single-candidate selector still delegates implementation preparation to the
current planner. Neither route authenticates a reviewer label, authorizes
execution or spending, connects a provider, measures benefit or activates JEV.
The durable end-to-end repository session and broader epic remain open.

## Integrated checks

The supplied partial-tree results (189 named tests and eight mutation
detections) are historical checkpoint evidence. The current integrated checks
used a native Ubuntu/Python 3.12.3 copy of the worktree. Its first complete
run, before the new installed-wheel test was added, passed 1,248 tests with
four skips. The installed-wheel test then passed separately. The final complete
run passed 1,249 tests with four skips. The release manifest is checked after
this report and the checksum rebuild.

| Check | Integrated result |
|---|---|
| New repository-scope API and CLI | 126 passed on native Ubuntu; includes central CLI routing and redacted malformed arguments |
| New installed-wheel negative outcome | 1 passed from an installed full evaluator wheel; synthetic host source was read, not imported or executed |
| First complete `python -m pytest -q` | 1,248 passed, 4 skipped before the new wheel test was added |
| Final complete `python -m pytest -q` | **1,249 passed, 4 skipped** |
| Package validator | 44 mirrored schemas; 321 synthetic research records; 13 implementation examples; one offline replay; no target execution or network |
| `validate_package.py --check-manifest` | 737 exact release files verified |
| Schema builder | Recreated all four mirrored contract pairs without byte changes |
| v1.1 and v1.2 offline demos | Passed with synthetic needs-more-evidence outcomes |
| A–M implementation demo | All 13 recipes passed, with no target left applied |
| Discovery/review and dev7 selection demos | Passed; synthetic discovery did not execute a host; dev7 synthetic lifecycle restored its target |
| New repository-scope demo | Passed: experimental selection and a separately reviewed bounded no-useful outcome, with unknown estimates retained |

The four local skips are three native-Windows rejection checks and one optional
TypeScript-parser check unavailable in the local Ubuntu environment. Hosted
exact-head interpreter/TypeScript checks are recorded in the PR. No independent
host corpus, live provider, application benefit or production activation was
qualified by these tests.
