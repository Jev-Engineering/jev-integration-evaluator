# Changelog

## 1.3.0.dev10 — mixed scope-review conflict guard

- Block experimental selection when an approved candidate conflicts with a
  negative judgment on its exact seam or entire source file, even when another
  reviewed source is useful. Retain requested IDs and failure denominators.
- Preserve consistent mixed reviews and the existing no-review experimental
  path. No runtime, recipe, provider or activation authority changes.
- Reject a useful seam judgment inside a negatively reviewed whole file, even
  when the seam was not nominated. Bound and snapshot scope-review input before
  validation so later caller mutation cannot change a prepared decision.
- Add source-matched regressions and refresh engine-bound synthetic examples.

## 1.3.0.dev9 — pattern-by-pattern repository conclusions

- Add a read-only `repository-discovery --stage conclude` operation with
  complete file/seam A–M opinions, objective and engine binding, unresolved
  denominators, and an independently retained review-digest requirement for a
  bounded negative conclusion.
- Preserve dev8 `repository-placement` and dev7 selection contracts. The new
  conclusion is an additional review artifact, not implementation authority,
  provider qualification, production activation or measured benefit.
- Add strict mirrored schemas, a fresh synthetic demonstration, installed-wheel
  and adversarial checks, and the dev9 validation record.
- Keep release ZIP manifest paths in the same portable order as the checksum
  rebuilder, so building an archive preserves the validated release manifest.

## 1.3.0.dev8 — reviewed repository-scope outcomes

- Add a source-revalidated repository placement context that distinguishes
  incomplete coverage, no discovered candidates, unsupported shapes and a
  bounded, complete-source reviewed no-useful-placement judgment.
- Add a central `repository-placement` command, strict mirrored contracts,
  source-linked synthetic examples and adversarial regression coverage.
- Preserve the dev7 planner-backed selector and its tests. The new set review
  is read-only and does not compose edits, authenticate approval or establish
  measured benefit. See `validation/SCOPE-OUTCOME-VALIDATION-1.3.0.dev8.md`.

## 1.3.0.dev7 — experimental placement selection

- Add a source-bound, externally approved experimental-selection contract that
  permits plan preparation with explicitly unknown benefit and cost estimates.
  Preserve estimate-based optimizer requirements and deterministic exclusions.
- Add strict mirrored schemas, a metadata-only standalone CLI, an offline
  synthetic lifecycle demonstration, installed-wheel and adversarial tests.
- Keep the existing implementation planner responsible for source, binding,
  recipe and policy checks. No live provider, production activation or measured
  benefit is established. Issue #7 and its dependency #5 remain open.
- Current qualification is recorded in
  `validation/SELECTION-VALIDATION-1.3.0.dev7.md`.

## 1.3.0.dev6 — review exclusion and batch safety

- Reject semantic reviews that clear a hard-real-time gate, remove a preferred or mandatory deterministic exclusion, or downgrade a mandatory exclusion to preferred.
- Validate every review before changing the inventory, reject duplicate candidate IDs, and detach mutable review input. Preserve candidate/list references on successful review for existing trace consumers.
- Add 65 synthetic regression cases covering exclusion retention, failed-batch atomicity, alias compatibility and scoring behavior. The dev5 discovery and inventory bridge remains available; issues #5 and #7 remain open for their separate outstanding acceptance work.
- Current qualification is recorded in `validation/REVIEW-GATE-VALIDATION-1.3.0.dev6.md`. No provider connection, activation or measured benefit is established.

## 1.3.0.dev5 — source-matched inventory and semantic review

- Add read-only `repository-discovery` discover/prepare/review stages to the installed CLI, with mandatory private external output and redacted status/error summaries.
- Reuse dev4 discovery and the existing candidate, scoring and review constructors. Bind preparation to the complete source snapshot, policy, parser and bridge implementation. Reject stale or caller-forged inventories.
- Apply deterministic and hard-real-time exclusions to every candidate, including heuristic discoveries. Semantic reviews cannot add measured estimates, weaken exclusions, approve bindings or authorize execution/activation.
- Add three mirrored inventory/review contracts, source-linked synthetic examples, adversarial regression tests and installed-wheel pipeline qualification. Preserve all dev4 discovery contracts and source/platform guardrails.
- Integrate the partial checkpoint without replacing the published analyzer with its older alternate implementation. Issue #5 and the wider implementation roadmap remain open; a complete reviewed no-useful-placement conclusion remains outstanding.
- Qualification is recorded in `validation/SEMANTIC-BRIDGE-VALIDATION-1.3.0.dev5.md`. Discovery and the review demonstration execute no target code; existing implementation demonstrations remain synthetic host-wiring evidence.

## 1.3.0.dev4 — source-bound discovery and nominations

- Integrate the supplied issue #5 checkpoint into the complete evaluator. Add bounded read-only Python capability discovery, opaque-name source/AST anchors, package/test/configuration sightings, static registry possibilities and explicit incomplete-coverage outcomes.
- Admit strict source-hashed nomination records against a freshly recomputed, externally retained report digest and caller-owned policy. Keep semantic review, binding review, benefit, execution qualification and authority unresolved.
- Expose `discover-capabilities` and `nominate-candidate` in the main CLI, preserve the standalone module/script, and register all three mirrored contracts with package and CLI validation.
- Qualify the complete installed package and parser-specific synthetic examples. Keep the legacy scanner, transformations and runtime behavior intact; discovery uses POSIX descriptor-relative access and does not import target code or invoke target tooling.
- Harden JSON input reads against linked/special files and preserve bounded, redacted failures. Correct conditional rebinding, local-scope and shadowed/decorated-callee classification; reject misleading generator and invalid/reserved-module structural preflight hints.
- This is a partial contribution to issue #5. The nomination-to-inventory/semantic-review bridge, repository session command and the remaining roadmap are outstanding. No provider connection, production activation or measured benefit is established.
- Current executed qualification is recorded in `validation/DISCOVERY-VALIDATION-1.3.0.dev4.md`; previous validation records remain historical.

## 1.3.0.dev3 — complete failure receipts and source fidelity

- Add the strict mirrored `implementation-observation` contract, recipe-bound trace roles/arity and bounded counters. Invalid probe output becomes a failed scheduled case with no invalid payload copied into the receipt.
- Record unavailable authorized command executables as `not_run`, preserve the full case schedule and block a passing receipt. Reject embedded NUL command arguments during planning rather than failing during execution.
- Check the exact ordered case/mode schedule, completion count, command digests and observation validity when loading receipts. Passing-shaped, self-consistently rehashed documents cannot replace a reviewed execution schedule.
- Fsync start events before baseline and modified execution. Interrupted or terminated re-verification blocks stale successful status and stale-baseline apply until fresh authorized verification or matching owned-byte rollback. Baseline checks preserve prior rollback and incomplete-mutation states.
- Keep generated imports ahead of unrelated decorators, including parenthesized multiline forms. Validate declared UTF-8 encoding and reject non-UTF-8 or invalid cookies before bundle creation. Selected decorated seams remain unsupported.
- Reject contradictory command status/exit-code receipts. Bound aggregate receipt output while retaining overflow observations as failed scheduled cases.
- Add focused regressions, including real subprocess termination, CLI contract validation, modified-host execution and byte-exact rollback; update package validation, CI selection, examples and support documentation together. Integration preserves the additional PR #16 safety fixes and their regressions.
- Retain dev2 safety fixes, existing public names, commands and valid receipt shapes. Old receipts remain tied to their engine identity; new observation/schedule checks tighten validation rather than recertifying historical evidence. No new runtime dependency, live model request, production activation or measured-benefit claim.
- Current execution and publication status are recorded separately in `validation/SAFETY-VALIDATION-1.3.0.dev3.md`; older validation files are historical and unchanged.


## 1.3.0.dev2 — executable-integration safety follow-up

- Preserve host exception objects and exactly-once effects even when executors, finishers, recovery callbacks or guard cleanup raise `PolicyBlock` or `UseFallback`. Router fallback cannot replay an attempted host operation. Off/shadow baseline calls run outside router-signal handlers.
- Retain bounded process-local weak-reference ownership tombstones after a router/coordinator is collected; recreating either object does not reset the existing workflow's budgets. Host-selected new scopes still require separate review/receipts.
- Reject parameter-shadowed seam/registry/executor bindings, exception/match-capture rebinding, and rebinding in module-level definition expressions before target mutation. The supported source shape is unchanged; previously accepted ambiguous shapes now fail closed.
- Bind isolated probe copies to the exact reviewed phase hashes/modes, retain raced or unavailable cases in the denominator, and recheck all integration-owned files after the authorized command. A successful command that changes/removes the generated adapter cannot establish verified state.
- Add backward-readable `file_identity_valid` receipt metadata in both schema copies. New receipts record the final check; `false` cannot accompany `passed`. Historical receipts without the field remain identifiable through their engine digest, not retroactively recertified.
- Add focused regression files to package validation and the Python-only CI job. No new dependencies, source-shape expansion, activation bypass, live provider claim or application-benefit claim.
- This development follow-up requires its own signed publication/review/CI qualification; local execution is recorded separately from historical dev1 evidence.

## 1.3.0.dev1 — bounded executable integrations

- Added strict reviewed binding specifications and executable AST-selected host edits for thirteen A–M Python recipes; no caller-authored replacement source required.
- Added complete plan/baseline/apply/modified verification/status/rollback CLI and matching scripts, with protected exact digests, original/applied identity separation, private preimages, fsynced recovery journals and process-interruption recovery.
- Added semantic Choice-to-host-action mappings bound into strict runtime receipts/cache contracts without changing legacy no-mapping hashes or adding model labels to host permissions.
- Added pattern-specific guarded behavior, independent post-action state observations, pinned context retention, explicit graph revision/approval checks, bounded plans/retries/delegation and retained partial/child outcomes.
- Added actual edited-host synthetic verification, externally anchored receipt status, code-owned call/effect assertions, full offline A–M demo, failure-injection tests and installed-wheel host checks.
- Source support is deliberately narrow and rejects unsupported Python shapes, dynamic registries and JS/TS rewriting. All implementation verification is synthetic; no live deployment, benefit or provider/bootstrap certification is claimed.
- No new runtime dependency. Older validation evidence remains historical. This is a development build pending whatever repository publication/review/CI qualification is recorded in the delivery report.

## 1.2.0 — 2026-09-26

### Implemented

| Area | Change | Executable components |
|---|---|---|
| Uncertain placement sets | All-scenario feasibility, worst-case utility, minimal retention, common-feasible-set minimax regret, prerequisite closure and conservative interaction credit | `scenarios.py`, `optimize-robust` |
| All-placement evidence | Every source-bound gate frozen in a paired study; role-sensitive rubric identity; raw holdout recomputation; cross-stage task/cluster leakage and familywise alpha allocation | `gates.py`, `study.py`, extended study commands |
| Shared operational budgets | Atomic process-local task/lifetime call and cost reservations, bounded concurrency, nonrefundable failed requests, tombstones and known-overrun suspension | `budget.py`, `runtime.py` |
| Exact runtime lifecycle | Configuration/question-role/canary-scope/shared-limit receipt binding; new factories require both expiring and runtime-bound receipts | `runtime.py`, `implementation.py`, activation schema |
| Canary monitoring | Frozen task/arm/cohort windows, full denominators, unknown metric handling, safety-event preservation, absolute/comparative limits, descriptive action-mix drift and explicit suspend-only host hook | `monitoring.py`, `cohorts.py`, two monitoring commands |
| Delivery | Six new schemas, compatible study/run/activation extensions, templates, v1.2 guide, 17-command synthetic demo and regression/property tests | `schemas/`, `scripts/`, `templates/`, `tests/` |

### Corrections and compatibility

Requests use separate validated/client state and question snapshots. Audit failures cannot populate the assessment cache. Cached inference tokens no longer count as new inference in source-correlated traces. Model calls remain proposals, not side effects. Legacy v1.0/v1.1 commands, fixtures, single-gate studies and direct `SafeRouter` constructor defaults remain supported. Newly generated factories require v1.2 receipt binding; do not weaken that factory merely to reuse an old receipt.

The optimizer's scenario assumptions and additive resources are explicit; beam search is not certified optimal. Shared budgets are not distributed, resetting a ledger is a new scope, and local evidence hashes are not signatures. Monitoring is not sequential statistical inference. No live model request, effectiveness study, production calibration, deployment or Git publication was performed. Executed validation is recorded in `validation/VALIDATION.md`; prior evidence is clearly separated under `validation/history-v1.1/`.

## 1.1.0 — 2026-09-26

This release extends the existing 47-section placement workflow with version-aware source review, stronger experimental contracts, rubric robustness probes, and runtime lifecycle controls. It does not claim live JEV performance improvements.

### Implemented

| Area | Change | Executable components |
|---|---|---|
| Snapshot lifecycle | Source/configuration/settings/analyzer/parser-coverage fingerprints; conservative candidate comparisons; reverse static dependency impact; line shifts, possible moves and uncertain absence; no inherited approvals. | `lifecycle.py`, `scan`, `diff` |
| Frozen studies | Exact task/replicate schedules, disjoint split identities, frozen code/model/policy/prompt versions, endpoints and analysis settings; failures/timeouts stay in the denominator; explicit held-out evidence binding. | `study.py`, `study-freeze`, `study-check`, `study-evaluate` |
| Held-out risk checks | Frozen per-label probability floors and confidence gate, complete holdout schedule, exact one-sided binomial error limits, prespecified subgroup checks with multiplicity adjustment, synthetic-evidence rejection. | `holdout.py`, `threshold-freeze`, `threshold-check --enforce` |
| Rubric robustness | Deterministic linter; original/retest/reordered/opaque-label/rotated-binding probes; exact order-sensitive request identity, semantic-map validation, normalized comparisons and explicit failed-probe accounting. | `robustness.py`, four rubric/robustness commands |
| Runtime lifecycle | Per-action thresholds that cannot weaken global limits; optional strict expiring receipts; ordered-rubric identity; revocation, latched suspension and in-flight rechecks; new adapter factories select strict receipts. | `runtime.py`, `implementation.py` |
| Audit and release integrity | External audit head/length checkpoints detect suffix truncation; package checks reject added, missing, duplicate or unsafe manifest entries. | `traces.py`, `verify-log`, `validate_package.py` |
| Delivery | Six additional schemas; readable diff/holdout sidecars; offline lifecycle example; input templates, migration guide and regression tests. | `schemas/`, `scripts/run_v11_demo.py`, `references/lifecycle-and-evidence.md` |

### Corrections

Configuration-only changes now alter scan identity. HTTP serialization and assessment cache keys preserve Choice presentation order. A decision-accuracy-only comparison cannot produce a downstream-task keep recommendation. Scanner Git metadata collection disables configured filesystem-monitor execution. Suspended routers do not retain newly completed assessments in their cache.

### Validation

296 tests pass (121 added); 16 schemas validate; the offline lifecycle and outside-checkout wheel smoke pass. See `validation/VALIDATION.md` and its raw evidence.

### Compatibility

Existing v1.0 commands and fixture-key behavior remain supported. Existing `compare` remains an exploratory tool; use `study-evaluate` for the stricter scheduled-study gate. Inventory/run schemas retain their compatible version fields and add optional metadata. New frozen contracts use schema version `1.1`.

`SafeRouter` keeps legacy receipt handling unless `require_expiring_activation=True` is supplied; newly generated `create_router` factories supply it automatically. Old exact fixtures retain canonical keys by default. Robustness probing requires `FixtureClient(..., order_sensitive=True)` and its newly generated request hashes. HTTP requests preserve caller-provided insertion order rather than sorting Choice labels.

### Boundaries

A fresh scan is still a full scan, not incremental parsing. Local digests/timestamps are not signatures or proof that a holdout was previously unseen. Independent IDs cannot prove statistical independence or label authenticity. The five probes inspect one state's response invariance, not population accuracy or adversarial security. Active proposals still do not execute actions or grant permission. No deployment, publication, live model call, or effectiveness claim is included in this release.

## 1.0.0

Original placement discovery, A–M patterns, scoring/optimization, runtime, approved patch workflow and evaluation toolkit. The original ZIP remains the authoritative historical artifact; v1.1 does not rewrite its evidence.
