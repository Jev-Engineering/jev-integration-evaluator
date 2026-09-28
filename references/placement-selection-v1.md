# Source-reviewed placement outcomes and experimental selection

**Historical component scope:** The issue #5/#7 development-status statements
below describe this component when introduced. Later roadmap acceptance is
recorded in the [final ledger](../roadmap-acceptance-ledger.json). The separate
[composite transaction](composite-transactions-v1.md) now handles its bounded
multi-placement mutation path.

This source-revalidated repository-scope component distinguishes outcomes needed
by issue #5 and offers read-only experimental set review for issue #7. It is not
the durable repository implementation command, an executable recipe, an
implementation bundle, or authorization to run a provider. The dev7
`selection.py` contract remains the single-candidate path into existing Python
plan preparation; this component never substitutes for that planner.

## Callable preparation stages

`prepare_placement_context` reconstructs the existing capability report,
nomination admissions, opportunity inventory and semantic review using
`nomination_inventory.review_nominated_inventory`. It compares the actual
source, configuration, policy, parser and analyzer identities. Caller-authored
inventories, rehashed changes and source-stale reviews are not accepted.

`select_experimental_placements` accepts a separate, explicit selection review
of the exact context and requested candidate set. All requested placements must
pass the existing deterministic and hard-real-time exclusions, source-matched
semantic review and supported-shape preflight. A rejected, unknown, conflicting
or unsupported member blocks the entire set. The result retains every requested
ID, its denominator and the failures; it never presents a partial set as a
success. Multiple selected placements require the separate bounded
[`implement-composite-*` transaction](composite-transactions-v1.md) where its
source and ownership conditions are met. Selection does not compose or apply
source edits.

`revalidate_experimental_selection` reconstructs the complete decision and checks
an independently retained selection digest before a consumer can use a saved
record. Neither a reviewer name nor a hash authenticates authority. No selection
record grants execution, mutation, installation, egress, publication or activation
permission. All of those fields remain false. A consumer still needs genuine
semantic/binding review, the supported implementation specification, externally
supplied execution scope and exact reviewed bundle-digest mutation approval.

The existing optimizer retains its dev7 evidence gates. Its missing estimates and empty feasible
integration set remain distinct from semantic absence. Experimental selection
preserves all unknown estimates as `null`, including cost and benefit. Optional
maximum calls, maximum USD cost and deadline bounds are retained as separate
constraints; they are not estimated usage, a budget reservation or spending
permission. Unknown bounds cannot cause spending through this component, which
has no provider-execution path. A bounded selection is not evidence of benefit,
an adoption recommendation or a way around the existing measurement-based tools.

## A negative judgment is not an empty inventory

A complete `repository-scope-review-v1` records a reviewer, reasoning, the exact
report/preparation digests, every enumerated file's entire-file source anchor,
and every enumerated seam's AST anchor. Each file and seam has an explicit
`no_useful_placement`, `useful`, or `unresolved` judgment over the existing A–M
placement taxonomy. There must be no duplicate, unknown, stale or missing row.
A completely empty repository does not pass by vacuous truth.

Only complete analysis plus a complete, all-negative source review can produce
`no_useful_placement`. An approved candidate contradicts a negative judgment
on its exact seam or entire source file even when another reviewed source is
useful. Such a conflict produces `insufficient_evidence` and blocks selection
while retaining every requested candidate in its denominator. A useful seam
judgment inside a negatively reviewed whole file is also inconsistent even
when that seam was not nominated. Scope-review input is bounded before expansion
and copied before validation to preserve the reviewed decision. A negative
unselected seam alone does not reject a consistently positive selected seam.
Missing review rows remain in explicit denominators. Parser failures, unparsed languages, exhausted bounds
and withheld ambiguous candidates cannot be waived by a negative judgment.
A negative individual candidate review requires further scope review, not a
claim about the entire repository.

The conclusion is a **source-reviewed judgment within the enumerated policy
scope**, not a mathematical proof of universal absence or a measurement of
application behavior. The record explicitly says
`bounded_source_and_configuration_not_full_repository`. Excluded files, unknown
extensions, generated source, third-party dependencies and future recipes are
outside the conclusion. Exclusion counts and the actual policy identity are
retained. Synthetic fixture judgments remain synthetic; the caller must obtain
a genuine review for a real repository.

## CLI

The module, thin script and central `repository-placement` command expose the
same operations. From the trusted source checkout:

```text
python -I scripts/select_repository_placements.py context --repo TARGET --report REPORT.json --prepared PREPARED.json --semantic-review REVIEW.json --config-json CONFIG.json --out NEW_CONTEXT.json
python -I scripts/select_repository_placements.py select --repo TARGET --report REPORT.json --prepared PREPARED.json --semantic-review REVIEW.json --config-json CONFIG.json --selection-review SELECTION_REVIEW.json --out NEW_SELECTION.json
python -I scripts/select_repository_placements.py revalidate --repo TARGET --report REPORT.json --prepared PREPARED.json --semantic-review REVIEW.json --config-json CONFIG.json --selection-review SELECTION_REVIEW.json --selection SELECTION.json --expected-selection-sha256 EXTERNALLY_RETAINED_DIGEST --out NEW_CHECKED_SELECTION.json
python -m jev_integration_evaluator repository-placement context --repo TARGET --report REPORT.json --prepared PREPARED.json --semantic-review REVIEW.json --config-json CONFIG.json --out NEW_CONTEXT.json
```

With the module installed, `python -I -m
jev_integration_evaluator.placement_selection` exposes the same arguments.
Use `--scope-review SCOPE_REVIEW.json` for the independently supplied scope
judgment and repeat the same external `--policy POLICY.json` wherever one was
used during discovery. Configuration defaults are the existing evaluator
defaults; changed effective configuration requires fresh preparation/review.

Every input must be external to the target. JSON is bounded, plain data: duplicate
keys, non-finite numbers, unsupported object types and extra authority fields
are rejected. Secure input reads reject symlinks, hard links and special files
without blocking on FIFOs. Outputs must be fresh files in an existing directory
outside the target; POSIX creates them with mode 0600. They are exclusive and
are not overwritten. Windows behavior of this broader placement-selection
workflow remains unqualified; the owner-only DACL contract applies to the base
`repository-discovery` command only. Stdout exposes only stable
status/outcome/next-action codes and a
digest, not source, reasoning or candidate details. A blocked selection writes
its complete private failure record and returns exit 2. Invalid inputs also
return 2 with a redacted reason. A written context result returns 0 even when
its truthful next action is additional review or unsupported-scope resolution;
that is successful read-only preparation, not successful implementation.

## Contracts and examples

Four strict schemas are mirrored under root `schemas/` and package `data/`:
`repository-placement-context-v1`, `repository-placement-review-v1`,
`repository-placement-selection-v1`, and `repository-scope-review-v1`.
The schema builder reuses the exact existing source/estimate contracts. Schema
validation alone is not source revalidation or receipt authentication.

`examples/placement-selection` contains alternative positive and negative
synthetic reviews, their source and source-linked outputs. Their filesystem and
engine identities are historical after copying: moving the examples invalidates
them for a fresh operation. Generate fresh examples using
`python -I scripts/run_placement_selection_demo.py --out NEW_PRIVATE_DIRECTORY`.
Never reuse example digests as authority for a different host.

## Qualification boundary and remaining work

The integrated tests exercise the complete current package without target
imports or provider calls. The supplied component tests have been reconciled
with dev7 and retained under `tests/test_repository_placement_selection.py`;
the previously merged selector and its tests are preserved. The original
checkpoint's partial-tree and mutation results are historical, not release
evidence for this build. These tests are not an independently authored host
corpus or a measured application study.

The existing installed-wheel tests and hosted checks qualify package loading.
They do not establish installed-host runtime wiring or an OS security sandbox.

The base native Windows discovery command is qualified for local NTFS paths as
described in [`platform-support.md`](platform-support.md). The broader placement
selection workflow is not qualified on Windows by that discovery result. JS/TS,
methods, async seams, installed host wiring and composite mutation do not inherit
Python selection qualification. Package-aware binding, agent-drafted specs,
sessions/recovery, real isolation, runtime bootstrap and study/monitor collection
remain their separately tracked roadmap work. The current conflict correction
is qualified in `validation/SCOPE-CONFLICT-VALIDATION-1.3.0.dev10.md`;
`validation/SCOPE-OUTCOME-VALIDATION-1.3.0.dev8.md` remains historical.
