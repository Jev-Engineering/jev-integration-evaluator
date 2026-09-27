# 1.3.0.dev10 mixed scope-review conflict correction

The supplied `JEV_Roadmap_Checkpoint_245d847d.zip` was a partial dev8-based
patch, not a full checkout or release. Its 120 payload files matched the packet
manifest. On the current dev9 tree, the new regression reproduced four failures
among eight cases: a positive candidate could still be experimentally selected
when its own seam or whole source file had a negative scope judgment, provided
another scope row was useful. The standalone CLI returned exit 0 for that
contradictory selection. The failure did not establish live provider use or an
activation bypass.

The integrated guard compares each source-validated approved candidate with its
exact seam and entire-file judgments. A contradiction yields
`insufficient_evidence` and asks for reconciliation. Existing complete-negative,
unresolved, consistently positive mixed-review and absent-scope paths retain
their separate behavior. A saved context or selection from the old engine is
historical and requires a fresh source-matched review before reuse.

The subsequent `JEV_Review_Consistency_Checkpoint_245d847d.zip` added a
related contradiction: a useful seam inside a negatively reviewed whole file,
even if it was not nominated. It also supplied pre-expansion input-bound and
CLI regressions. The integrated code rejects that contradiction and snapshots
bounded review input before validating it. All 160 focused placement tests
passed together after integration. These are synthetic source fixtures, not
evidence of a live provider connection or production benefit.

## Integrated checks

On the current checkout under WSL Linux/CPython 3.12.3, the full test suite passed:
**1,370 passed, four skipped**. Three skips exercise native non-POSIX rejection;
the fourth requires trusted Node/TypeScript tooling absent from this local
environment. The 160 focused placement tests passed separately. Package
validation passed with 46 schemas and 321 synthetic records. The v1.1, v1.2,
13-recipe implementation, capability, selection lifecycle, placement-selection
and repository-conclusion offline demonstrations passed. Their outcomes are
synthetic; no target host or provider was contacted. The release checksum
manifest and hosted CI are checked separately during publication.
