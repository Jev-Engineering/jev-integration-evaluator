# Changelog

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
