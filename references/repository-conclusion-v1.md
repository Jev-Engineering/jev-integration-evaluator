# Source-reviewed repository conclusions, contract v1

**Unpublished implementation checkpoint against main `3f05735e67ac1163757050ad03d219f45d0fcf2a` (1.3.0.dev7).** This extension addresses issue #5's remaining distinction between incomplete analysis, unsupported implementation, no candidates and a complete scoped negative semantic opinion. It does not complete or release the repository-to-JEV roadmap.

## Invocation and review workflow

The installed CLI exposes an additional read-only stage:

```text
python -m jev_integration_evaluator repository-discovery TARGET --stage conclude --capabilities EXTERNAL_CAPABILITIES.json --out NEW_EXTERNAL_CONCLUSION.json
python scripts/conclude_repository.py TARGET --capabilities EXTERNAL_CAPABILITIES.json --coverage-review EXTERNAL_REVIEW.json --review-sha256 INDEPENDENTLY_RETAINED_REVIEW_DIGEST --out NEW_EXTERNAL_CONCLUSION.json
```

The thin script fixes `conclude`; it rejects an additional `--stage`. The existing discover, prepare and review stages are unchanged. `--objective`, `--config` and `--policy` bind the effective externally supplied objective, full evaluator configuration and discovery limits. Changing any of them requires fresh matching review inputs. A coverage review must be outside the target. Outputs are new private, descriptor-relative, exclusive mode-0600 files outside the target; existing outputs are never replaced. Exit 0 means an artifact was written, **not** eligibility, successful implementation, authorization or benefit. Inspect `outcome` and `next_actions`.

Generate the capability report using `repository-discovery --stage discover`. The Python API `coverage_review_schedule(report, cfg, objective=..., policy=...)` supplies exact file/seam anchors and the required A–M pattern names. It does not fill opinions, authenticate reviewers or certify current source. Read the complete listed source and review the file-level behavior as well as each discovered seam. Complete each required pattern with `not_useful`, `potentially_useful` or `unresolved` and a nonblank source-grounded reason. Missing facts must remain unresolved.

The strict `repository-coverage-review-v1` contract contains the report, settings, objective and conclusion-engine digests, reviewer claim, full-file hash/mode/line anchors and seam qualified-symbol/file/AST/line anchors. Every included file or seam row requires all thirteen opinions. Entire omitted rows remain pending; each adds thirteen missing opinions to the denominator. Unknown fields, duplicate rows, stale or invented anchors, contradictions and attempts to waive mandatory exclusions are rejected rather than repaired.

Authenticate the reviewer through an external trusted process and retain the reviewed record's canonical digest there. The canonical digest is SHA-256 over the existing capability JSON encoding (`sort_keys=True`, separators `(',', ':')`, UTF-8, `ensure_ascii=False`, `allow_nan=False`). Supply that retained value through `--review-sha256`. A claimed name or digest read from the same untrusted record is **not authentication**. This API verifies equality only and always emits `review_principal_authenticated: false`; external review trust remains the caller's responsibility. Never treat a recomputed self-hash alone as a trusted approval.

## Derivation and scope

`conclude_repository` discovers fresh source before evaluating a review and checks the complete capability record. It discovers again after evaluation and checks the engine identity again. Byte, mode, enumeration, policy, parser or relevant-engine drift invalidates the operation. Source is parsed, not imported, evaluated, compiled to bytecode or sent to a provider. Future consumers must still revalidate source; a past receipt is not a perpetual lease or atomic filesystem snapshot.

The review denominator is every file and seam in the current bounded capability snapshot, not merely nominated candidates or a heuristic shortlist. File-level review accounts for behavior outside discovered functions. A positive seam opinion cannot contradict a negative opinion for that pattern on its containing file or override a known deterministic/hard-real-time exclusion. A positive file opinion or unsupported seam remains unsupported/unresolved; a structural preflight is never recipe qualification.

| Outcome | Exact interpretation |
| --- | --- |
| `incomplete_analysis` | Coverage limits, missing parsers or unreadable/unparsed in-scope source prevent a complete conclusion, regardless of submitted opinions. |
| `no_candidates_discovered` | No files or structural seams were found in the bounded scope; this is not a negative semantic conclusion. |
| `review_required` | Discovered source needs source-bound file and seam review. |
| `insufficient_evidence` | Reviews are missing/unresolved or the separately retained review digest is absent. |
| `unsupported_or_unresolved` | Structural support is absent, or reviewed positive hypotheses have no established preflight. |
| `useful_placements_identified` | A complete anchored review identifies a potentially useful preflight seam; separate semantic-candidate and binding decisions remain required. |
| `no_useful_placement` | Complete anchored negative opinions cover every file, seam and A–M slot in this exact bounded snapshot and objective. |

`no_useful_placement` is a **scoped reviewed opinion**, not a universal absence proof. Every result retains `snapshot_scope: bounded_source_and_configuration_not_full_repository`, exclusion counts, `global_absence_proven: false`, unknown benefit, no binding review, no implementation verification and false execution/mutation/egress/activation flags. An empty repository cannot satisfy a negative semantic conclusion vacuously. Missing measurements are never converted into zero cost, no benefit, adoption claims or absence of useful placements.

## Bounds, platforms and unsupported capabilities

Both input and output records have a 16,000,000-byte implementation bound; schema arrays and source scanning have additional published limits. Secure path operations inherit the discovery contract's POSIX descriptor-relative/O_NOFOLLOW requirement. The actual checkpoint qualification is Linux, CPython 3.13.5 only. Native Windows behavior, other interpreters, new parser backends, package/async/method rewrite support, operating-system execution isolation, the independent issue #9 corpus, live connectivity and activation are not qualified by this extension. No isolation or process/resource sandbox is claimed for AST parsing.

`validate --kind repository-coverage-review-v1` and `validate --kind repository-conclusion-v1` perform bounded shape validation; conclusion validation also checks its self-digest. They explicitly return `source_revalidated: false`. A shape-valid or self-consistent record is not current trusted source evidence. A real conclusion must use the source-reading API or conclude stage.

## Fresh synthetic examples and tests

```text
python scripts/run_repository_conclusion_demo.py --out NEW_EXTERNAL_PRIVATE_DIRECTORY
python -m pytest -q tests/test_repository_conclusion.py tests/test_repository_conclusion_cli.py tests/test_repository_conclusion_wheel.py
python scripts/rebuild_repository_conclusion_schemas.py
```

The demo accepts **no target repository**: it creates a built-in synthetic source fixture and emits its actual capability report, unfilled review schedule, synthetic opinions and three distinct outcomes. Its reviewer is an assistant-authored fixture identity, not an authenticated person. Regenerate reports on each interpreter/installation; persisted example hashes are historical and cannot authorize a different path or source snapshot. The demo never executes even its synthetic source. These fixtures do not satisfy independently authored corpus qualification under issue #9.

Root `schemas/` and installed `jev_integration_evaluator/data/` contain identical v1 contracts. The installed-wheel regression builds and installs offline, imports from the installed directory outside the checkout, runs the actual CLI, checks private outputs and unchanged source, then verifies rejection after source drift.

## Delivery boundary

No signed commit, PR, merge or release is asserted by this checkpoint. Issue #5 remains open until independent review, complete current-repository qualification, release metadata/checksum updates, exact-head hosted checks and normal merge complete. The selector's persistence in issue #4 and all other remaining child/epic criteria remain separate work. Do not close issue #5 or remove dependency links merely because this local patch exists.
