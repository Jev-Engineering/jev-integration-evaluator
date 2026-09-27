# Multi-placement evidence and operational controls — v1.2

## What this release changes

The v1.1 workflow remains available. This extension addresses four additional questions: does a placement set remain useful under declared adverse assumptions; does every active acceptance gate have matching evidence; do all placements share the same workflow budget; and does a canary still meet its explicitly frozen operating limits?

```text
Fresh reviewed source inventory
→ explicit nominal/adverse scenarios → robust placement set
→ each gate: calibration → frozen thresholds → complete independent holdout
→ freeze every gate/source/evidence identity in the downstream paired study
→ collect every scheduled baseline and combined-treatment outcome
→ independent review and exact-runtime approval
→ shared-budget shadow/canary operation
→ frozen complete operational windows → continue current exposure / inspect / suspend
```

A scenario result, a passing holdout, a study `keep`, or a healthy monitoring window is not deployment approval. The host still owns current-state checks, capability registration, permissions, irreversible-action approval, execution, and independent provenance. No new command transmits evidence or runs a target application.

## 1. Robust placement selection under explicit uncertainty

`optimize` remains the original point-estimate optimizer. The separate `optimize-robust` command evaluates declared sensitivity scenarios. It does not manufacture a probability distribution or transform heuristic scoring intervals into confidence intervals.

```bash
python -m jev_integration_evaluator optimize-robust \
  --inventory reviewed/jev-opportunities.json \
  --spec scenarios.json --config analysis-config.yaml \
  --out robust-placement-sets.json
```

Start from `templates/scenario-spec.example.json`, replacing every example candidate ID and assumption with evidence for the current source. Each scenario needs an ID, `evidence_type` (`observed`, `assumed`, or `synthetic`), provenance, and a complete estimate vector for every candidate it includes. The vector contains the four benefit dimensions, latency, cost, calls, complexity, maintenance, false-positive/negative rates, risk and throughput. Missing or unknown values are not zero: that candidate becomes ineligible when any scenario lacks its estimates. An explicit null, malformed number or incomplete vector is an input error.

Admission also requires a nonzero tier and a source-matched semantic review with an approver and rationale. Deterministic-preferred/mandatory, hard-real-time and `NONE` anti-patterns remain rejected even when a record has a misleading positive tier. Approval of an authored demonstration fixture is not a general rule for approving arbitrary code.

The `requires` map declares candidate prerequisites. Missing references and cycles are errors. Ineligible prerequisites exclude their dependents. Inventory conflicts remain forbidden. Scenarios may contain explicit interaction deltas; positive credit requires `status: measured` and provenance. Unmeasured positive synergy receives zero credit. Negative assumed interaction penalties are allowed. A `measured` string alone does not authenticate a study.

All selected placements must meet the configured resource constraints in **every** scenario. Latency/cost/calls/complexity use serial additive totals; risk and throughput are per-placement limits. These are engineering approximations, not a queueing model, combined risk bound or end-to-end throughput guarantee.

The report contains:

- A **balanced set** maximizing the minimum utility across scenarios, with utility weights fully disclosed.
- A **minimal set** retaining the requested fraction of the balanced set's positive worst-case utility, preferring fewer calls and placements.
- A **minimax-regret set**, minimizing the largest regret relative to each scenario's best set within the **common feasible set**.

The empty baseline is always a candidate. When no set has positive worst-case utility, the result is `no_robustly_useful_integration_set`. No unnecessary model calls are recommended simply to populate a result.

Small problems use exhaustive enumeration. The implementation switches to a bounded-width dependency-closure beam for larger problems or when the enumeration/scenario product exceeds its limit. Beam outputs explicitly withhold an optimality claim; their regret comparator covers retained states only. Neither approach covers omitted scenarios. There is no hard execution-time guarantee.

## 2. Bind every gate to actual held-out evidence

A v1.1 study can still use its single legacy `holdout_binding`. A v1.2 all-gate study instead declares `deployment_gates`, `placement_inventory_fingerprint`, and `gate_familywise_alpha`. Mixing both contracts is rejected.

Each gate freezes its ID, candidate/source file and symbol, file/body hashes, model, policy version, full ordered questions, primary Choice question, exact acceptance policy, threshold-plan digest, and holdout-report digest. Different gates may use different model/policy identities; the top-level treatment identity still names the actual combined program.

A primary-question role is part of the rubric identity. Two questions can have identical label sets but mean different things. Use the new helper **before** generating calibration and holdout records:

```python
from jev_integration_evaluator.gates import gate_rubric_hash

rubric_hash = gate_rubric_hash(questions, pinned_model_id, primary_question="action")
```

This hash binds both presentation order and the question whose labels were scored. A v1.1 canonical or order-only hash is not interchangeable with it. Reusing old data requires reconstructing and independently verifying the original question-role binding, not relabeling a digest to force acceptance.

Each acceptance policy records the global selected-answer probability floor, provider-confidence floor, per-label probability floors, and abstention labels. The policy must exactly match the held-out check. Even apparently stricter thresholds cannot silently reuse the old certificate: a selected subset can have a different error rate. This gate does not claim to validate separate Noul inspection, baseline fallback, or host-security paths.

Build and validate each frozen threshold plan using the existing `threshold-freeze` and `threshold-check` commands. When retaining the holdout report for an all-gate study, pass the threshold plan's independently retained digest using `--expected-digest`; the report identity records that check. Allocate the overall alpha budget across gates. Existing pooled/subgroup alpha adjustment happens inside each gate; the sum of gate alpha allocations must not exceed `gate_familywise_alpha`.

Freeze the downstream study only after the per-gate evidence identities are available and before observing the downstream test outcomes:

```bash
python -m jev_integration_evaluator study-freeze \
  --spec all-gate-study-spec.json \
  --inventory reviewed/jev-opportunities.json \
  --config analysis-config.yaml --out frozen-study.json
```

The inventory must match the frozen scan identity. Each gate must point to a currently reviewed, nonrejected source boundary. Record the manifest digest in every scheduled baseline and treatment row as `gate_manifest_digest = digest(deployment_gates)`. Baseline rows use it as the comparison's identity; this does not imply that baseline executed those gates.

The gate bundle contains **every frozen threshold plan and all raw held-out observations**, not just a purported pass flag:

```json
{
  "schema_version": "1.2",
  "gate_manifest_digest": "REPLACE_WITH_ACTUAL_DIGEST",
  "gates": [
    {
      "gate_id": "REPLACE_WITH_REAL_GATE_ID",
      "threshold_plan": {"...": "complete frozen threshold policy"},
      "holdout_rows": [{"...": "every scheduled labeled observation"}]
    }
  ]
}
```

This illustration is not schema-valid data; the fully executable synthetic demo produces complete contracts. A bundle with missing, extra or duplicated gates is rejected. The evaluator recomputes each report from its plan and rows, then checks the previously frozen report digest, model/policy/rubric identity, exact acceptance policy and evidence classification. Calibration/holdout task hashes and cluster IDs cannot overlap downstream test units. This protects against explicit identity leakage, not hidden semantic duplicates or falsified labels.

```bash
python -m jev_integration_evaluator study-evaluate \
  --plan frozen-study.json --inventory current-reviewed/jev-opportunities.json \
  --baseline baseline.jsonl --jev combined-treatment.jsonl \
  --gate-bundle all-gate-evidence.json \
  --expected-digest RETAINED_STUDY_DIGEST \
  --out all-gate-results.json --enforce
```

A missing bundle yields `needs_more_evidence`, not adoption. All gates must qualify with observed evidence, the externally retained study digest must match, and the existing paired task-level usefulness/resource/safety checks must also pass. Synthetic evidence can pass numerical checks but never justify `keep`. An independently reviewed joint treatment study is still necessary; independently good gates do not prove that their combination is good.

## 3. Share one real budget across placements

Per-router budgets remain useful but cannot bound a whole workflow when several routers each get their own allowance. Use **the same `BudgetCoordinator` object** for every participating placement:

```python
from jev_integration_evaluator.budget import BudgetCoordinator

shared_budget = BudgetCoordinator(
    max_calls_per_task=5,
    max_cost_per_task=0.02,
    max_total_calls=500,
    max_total_cost=2.00,
    max_in_flight=4,
    max_tasks=2048,
)
```

The amounts are illustrative operator-defined limits, not provider prices. Supply a defensible cost upper bound for each call. Every router reserves a call and that bound atomically before inference. Failures, timeouts and audit errors do not refund the reservation. Cached assessments make no new inference reservation. A known cost above the declared bound charges the excess and suspends the shared ledger; it cannot undo a provider charge already incurred.

The coordinator is **process-local and thread-safe**, not a distributed quota service or provider-enforced spending cap. Separate instances/processes have separate scopes. Do not claim an organization-wide limit without an appropriate shared host service. Lifetime call/cost totals never reset. `close_task(task_id)` tombstones that task and invalidates its in-flight/cached proposals; completed task identities consume registry capacity. A full registry refuses new tasks rather than forgetting past spend. Creating a new ledger is a deliberate new budget scope, not automatic rollover. Receipts bind the declared shared limits, not a persisted ledger identity; the trusted host must prevent replacing the ledger with a fresh instance merely to reset counters.

`SafeRouter` accepts `budget_coordinator`, `max_concurrent_calls`, and `canary_scope`. Shared concurrency is checked across routers; local nonblocking concurrency admission also bounds active requests. All placements in a combined canary treatment should use the same stable task ID and canary scope so task assignment remains consistent. Mixing policy-version salts previously could put different gates in different arms.

```python
# The generated create_router factory enables the two strict receipt checks.
router = create_router(
    client,
    runtime_config,
    activation=independently_approved_receipt,
    budget_coordinator=shared_budget,
    max_concurrent_calls=4,
    canary_scope="reviewed-combined-treatment-v1",
)
```

The host must aggregate a whole task to one stable ID. Changing IDs, rebuilding ledgers, or mutating host code can defeat local accounting; the library does not authenticate the host.

## 4. Bind activation to the entire operational policy

Existing direct constructors retain legacy defaults for compatibility. Newly generated factories require both `require_expiring_activation=True` and `require_runtime_binding=True`. A v1.1 receipt alone cannot activate them.

The new `runtime_contract_hash(questions, primary_question, evidence_question)` binds runtime configuration, pinned model and ordered questions, question roles, global/per-action thresholds, policy version, concurrency, canary scope, and shared-budget limits. It includes prices, deadlines, cache and call settings, and exposure fraction through the runtime configuration. Changing these values invalidates the receipt rather than silently reusing an approval for a different operating policy.

Compute the hash from a router configured for the **exact intended** operating mode, without calling it or granting approval. A router without a valid receipt falls back. The independent approver then retains the inspected hash and issues the receipt. Computing a hash is not approval, and moving an already-approved off configuration to canary requires a new reviewed hash.

Strict receipts still require issue/expiry timestamps, actual model/policy/threshold/rubric identities and an independently validated evidence reference. For monitoring integration, retain `deployment_id` and `study_digest` as well. Use `templates/activation-v1.2.example.json` only as a shape example; it is deliberately unapproved, synthetic, and cannot activate a router.

Request state and questions are copied before evaluation, and the client receives another copy. An audit write failure cannot leave a reusable cache entry. Source trace aggregation counts cached inference tokens as zero new tokens. Suspension, expiry, task closure and shared-ledger suspension are rechecked before returning an assessment. A thread or already-sent request cannot be forcibly cancelled by these checks; the executor must still validate current authority at the real side-effect boundary.

## 5. Complete fixed operational windows

`monitor-freeze` records a complete task schedule, task-level canary assignment, required cohorts, deployment/study/runtime identities, action reference proportions, timestamps and deterministic operating limits. `templates/monitor-spec.example.json` supplies a synthetic shape example.

```bash
python -m jev_integration_evaluator monitor-freeze --spec monitor-spec.json --out monitor-plan.json
python -m jev_integration_evaluator monitor-check \
  --plan monitor-plan.json --input task-outcomes.jsonl \
  --expected-digest RETAINED_MONITOR_DIGEST \
  --out monitor-report.json --enforce
```

Each required cohort and the pooled window must contain enough assigned tasks in both arms. Task IDs, hashes and cluster IDs must be unique: aggregate correlated records at the intended task/cluster level instead of creating artificial sample size. Assignments use the same stable algorithm as the runtime, but deterministic hashing is not proof of randomization or representative sampling.

Each outcome identifies its task, arm, cohort, study, deployment, window, monitor digest, timestamps and evidence classification. Required metrics are success, latency, cost, unsafe actions, fallbacks, decisions and action counts. Unknown values are null, never invented. Action counts must cover **every** decision, including fallbacks, abstentions and unrecognized labels. Zero decisions or too few actions cannot produce a healthy decision-distribution check.

The monitor checks absolute failure and timeout rates, increased failure rate versus baseline, difference between arm p95 latencies, mean added cost, fallback rate, unsafe-action counts, and total variation from the frozen action distribution. Unknown labels retain their mass. The p95 statistic uses nearest rank; the difference between arm quantiles is not the p95 of paired latency differences.

Missing outcomes remain in the scheduled denominator. Comparative summaries are withheld for incomplete cohorts. A known unsafe event is retained as a lower bound even when that record has unknown cost. Incomplete windows beyond the reporting grace period, stale windows, and breached limits recommend suspension. Open windows, pending outcomes or insufficient action evidence cannot silently pass. A healthy synthetic window cannot qualify for continued canary operation.

These are **operational descriptive guardrails**, not sequential hypothesis tests, optional-stopping-safe probabilities, causal estimates, or a guarantee that drift means quality degraded. Repeated windows must not be presented as repeatedly confirmed significance. The `--as-of` option supports explicit offline replay; the host control hook always uses current time.

### Explicit host suspension hook

```python
from jev_integration_evaluator.monitoring import suspend_from_monitor

report = suspend_from_monitor(
    frozen_monitor_plan,
    complete_or_honestly_partial_task_rows,
    routers={"router-gate": router, "verifier-gate": verifier},
    expected_digest=independently_retained_monitor_digest,
    approved_deployment_id=explicitly_approved_deployment_id,
)
```

This is an opt-in host integration, not a CLI side effect. It recomputes the report from raw rows, requires observed evidence and an exact deployment/runtime-router scope, and checks the same canary salt/fraction. When necessary it latches the supplied routers off. It cannot resume, increase exposure, deploy, roll back previously executed actions, or cancel already-sent provider requests. Healthy reports do not reactivate previously suspended routers. Invalid or mismatched inputs raise `InputError`; the trusted host must separately decide how to suspend when instrumentation itself fails.

## 6. CLI status and migration

Without `--enforce`, producing a valid report exits 0 even when its conclusion is insufficient evidence or suspension. With `--enforce`, `study-evaluate` exits 3 unless it supports `keep`, `threshold-check` exits 3 unless activation evidence qualifies, and `monitor-check` exits 3 unless complete, fresh, observed, digest-pinned monitoring qualifies for continuation. Invalid input exits 2. Read the report; exit 0 never grants host authority.

The v1.0/v1.1 commands, legacy fixtures, existing direct router construction, and single-holdout studies remain supported. New all-gate studies use schema version `1.2`; compatible run records add `gate_manifest_digest`. Root and installed-package schema copies are identical. No new external runtime dependency is introduced. Scans are still full scans, not incremental parsing. Supported AST languages and explicit unsupported-language boundaries have not changed.

## Offline reproducibility

```bash
python scripts/run_v12_demo.py --out ../jev-v12-demo
python -m pytest -q
python scripts/validate_package.py
```

Use a new or empty output directory. The demo runs 17 CLI operations, evaluates two synthetic gates (80 calibration and 240 holdout observations total), 80 synthetic paired tasks, 80 monitoring tasks and three shadow submissions across two routers with only two admitted fixture calls. It asserts the expected synthetic enforcement failures. All observations are fabricated to exercise software contracts, not to measure JEV usefulness. Actual executed release checks and limitations are in `validation/VALIDATION.md`.
