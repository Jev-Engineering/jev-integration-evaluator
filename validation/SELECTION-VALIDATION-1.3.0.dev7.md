# 1.3.0.dev7 experimental selection integration

## Input and reconciliation

The supplied `jev-epic3-selection-checkpoint.zip` has SHA-256
`5ef076f70cae41e00310071f74ee5a8055678ba4def5e584be06a11947a5667e`.
All 35 payload checksums matched and the archive had no unsafe paths or
case-colliding names. Its embedded patch has SHA-256
`82c993ae9d29c3f7872ad93eb3a0a95269c9c147f5ba0d3056b6f2fbc141fb1a`.
The patch was prepared against dev5 main `e4f0c93` and applied cleanly to the
complete dev6 checkout at `6a27147`; dev6 did not change the optimizer preimage.
The supplied checkpoint was partial and unmerged. Its targeted test counts are
historical checkpoint evidence, not a complete-package qualification.

## Behavior and limits

Experimental selection binds the full inventory, selector source/schema identity,
source-matched semantic review and an externally approved request. Code
preparation additionally binds the implementation specification and delegates
fresh source, AST, recipe, binding and policy checks to the existing planner.
Unknown estimates remain null; the optimizer retains provenance and feasibility
requirements. Selection cannot grant target execution, mutation, provider spend,
activation or a keep decision. Negative status is scoped to the reviewed
inventory; a complete-source no-useful-placement disposition is still issue #5.

The new standalone module and thin script do not add a durable repository
session or general point-at-a-repository command. Installed-host packages,
native isolation, live connectivity, application bootstrap, measured benefit
and production activation are outside this synthetic qualification. Issue #7
and epic #3 remain open.

## Integrated checks

The native Ubuntu/Python 3.12.3 test copy was byte-matched to this worktree for
the source under test. The first full run had 1,121 passes, four skips and one
packaging-fixture failure: the validator still required the historical dev6
report even though the fixture copies only the current release report. The
validator now requires the current dev7 report. All four release-manifest tests
pass after that correction. The final full run passed with 1,122 passes and
four skips: three checks that verify rejection on native Windows and one optional
TypeScript-parser check unavailable in the local Ubuntu environment.

| Check | Integrated result |
|---|---|
| New selection API | 87 tests passed on Windows Python 3.14.3 |
| Package validator before checksum rebuild | 40 mirrored schemas, 321 synthetic research records, 13 implementation examples, three capability and six bridge examples, one offline replay; no target execution or network |
| Native Ubuntu full suite, initial run | 1,121 passed, 4 skipped, 1 release-fixture failure corrected as above |
| Native Ubuntu release-manifest regression after correction | 4 passed |
| Native Ubuntu final full `python -m pytest -q` | **1,122 passed, 4 skipped** |
| `validate_package.py --check-manifest` | 40 mirrored schemas; 707 exact release files; 321 synthetic records; 13 implementation examples; one offline replay; no target execution or network |
| v1.1 and v1.2 offline demos | Passed; both retained synthetic needs-more-evidence outcomes and no activation eligibility |
| A–M implementation demo | All 13 recipes passed with no target left applied |
| Discovery/review demo | Eight synthetic records; negative semantic opinion; no host execution or network |
| Selection demo with explicit synthetic lifecycle | Experimental selection and plan; unknown estimates retained; baseline 1/1, modified 3/3, status verified, rollback restored target |

Hosted exact-head CI and signed publication results belong to the PR and its
check runs. These local checks do not qualify real-host bootstrap, native OS
isolation, independently authored host corpus, provider connectivity, measured
benefit or production activation.
