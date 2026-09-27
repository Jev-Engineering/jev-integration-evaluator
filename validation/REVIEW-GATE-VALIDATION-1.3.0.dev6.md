# 1.3.0.dev6 review gate integration qualification

## Input and reconciliation

The supplied `jev-review-gates-checkpoint.zip` has SHA-256
`03b0b83abbe730224865964efafcdf6592f6fb3e8a0712a037624c347fefdab1`.
All 18 payload files matched its `SHA256SUMS` and exact file set. The embedded
patch has SHA-256
`4a03440354fee93817f62a121e0612a9d1fa824933d3fde3af1b96c77f51bf99`.
Its scoring, I/O and configuration baselines matched the corresponding files at
merged dev5 main `e4f0c93ea8c9216d395a6d992dcf7bba17639ef1`; its package
version baseline is older. The checkpoint was a partial test snapshot, not an
installable distribution, signed commit, hosted check or merged release.

The supplied scoring patch and 63 synthetic cases were applied to an isolated
worktree. Against the unchanged baseline, the new suite reproduced 49 failures
and 14 passes on Windows Python 3.14.3. Against the patch, all 63 passed. An
existing traceability test then exposed a compatibility regression: replacing
candidate objects left a previously held candidate reference stale. The
integration now stages the full batch and updates existing candidate/list objects
only after all reviews validate. The new compatibility regression and supplied
cases pass together.

## Behavior and limits

`apply_reviews` rejects attempts to clear a hard-real-time exclusion, remove a
preferred/mandatory deterministic exclusion, or downgrade mandatory to preferred.
It rejects duplicate candidate IDs and leaves the original inventory unchanged
when any update fails. Successful updates detach caller-owned review data while
preserving candidate/list references and deterministic ordering. No schema shape,
runtime default, provider call, source discovery rule, host mutation, or
implementation recipe is changed by this correction.

The checkpoint reported six mutation probes against its partial candidate
snapshot. That result is historical, synthetic, and not a full package or
independent host qualification. Current integrated checks are recorded below.
This change does not complete issue #5's reviewed no-useful-placement outcome,
issue #7's selection contract or the repository implementation roadmap. It does
not establish live connectivity, production activation or measured benefit.

## Executed integrated checks

An isolated byte-matched Ubuntu/Python 3.12.3 copy was qualified on 2026-09-27.
No Node/TypeScript parser was available in that local environment. The scripts
ran offline with synthetic fixtures; logs and input hashes were retained outside
the checkout.

| Check | Executed result |
|---|---|
| Full `python -m pytest -q` | **1,017 passed, 4 skipped**: three native-Windows-only checks and one unavailable optional TypeScript parser |
| `validate_package.py --check-manifest` | 34 mirrored schema pairs; 687 exact release files; 321 synthetic research records; 13 implementation examples; three capability and six bridge records; one observation and one offline replay |
| Installed-wheel paths (within full suite) | Existing implementation/discovery wheel suites and the bridge-to-existing-C-plan suite passed; no target execution or modification in the bridge test |
| v1.1 and v1.2 offline demos | Both passed; synthetic outcomes remain ineligible for activation |
| A–M implementation demo | All 13 passed; 21 baseline and 63 modified synthetic cases; every target restored |
| Discovery/review demo | Eight private source-bound records; negative synthetic semantic opinion; no target import, execution or network request |
| Native Windows Python 3.14.3 focused checks | 71 passed, 35 skipped for POSIX-only discovery paths; this does not qualify native Windows discovery |

The first complete local run, before the malformed untouched-candidate test and
sorting correction, had 1,016 passes and four skips. The final run above used
the corrected scoring code and refreshed bridge examples. Documentation and
`SHA256SUMS` were finalized afterward; the final package manifest and ZIP/wheel
payloads are checked again after those metadata edits. Hosted Python/TypeScript
and Python-only results belong to the eventual exact PR commit, not this local
record. The source review and synthetic tests do not constitute the independent
host corpus, authenticated semantic review, or a measured application outcome.
