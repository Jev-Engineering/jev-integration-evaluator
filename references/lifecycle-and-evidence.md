# Version-aware placement and evidence lifecycle — v1.1

## Operating sequence

Use this extension after the normal scan and source-led semantic review:

```text
Fresh scan → compare prior snapshot → review affected boundaries
→ lint and probe the proposed rubric
→ choose thresholds using calibration data
→ freeze thresholds and the untouched holdout schedule
→ validate the complete holdout
→ freeze the downstream paired-study schedule and identities
→ collect all scheduled outcomes → validate/evaluate
→ independently approve an expiring runtime receipt
→ shadow/canary/active operation with host policy and suspension controls
```

Approval to analyze does not authorize transmitting source, running target code, modifying a repository, spending on inference, or deploying. The commands below do not grant those permissions. Retain generated digests in an independently controlled system before collection; local timestamps alone cannot establish preregistration.

## 1. Fresh scans and change review

```bash
python -m jev_integration_evaluator scan --repo /path/to/repository --out ../snapshot-before
# After the repository changes, run a complete fresh scan.
python -m jev_integration_evaluator scan --repo /path/to/repository --out ../snapshot-after
python -m jev_integration_evaluator diff \
  --before ../snapshot-before/jev-opportunities.json \
  --after ../snapshot-after/jev-opportunities.json \
  --out ../change-review.json
```

`diff` also writes `change-review.report.md`. Candidate states are `new`, `changed`, `unchanged`, `line_shift_only`, `removed`, or `not_observed`. An unchanged body may still require review because its containing file, repository configuration, analysis settings or a known static dependency changed. Exact-body move matches are suggestions, never automatic ID/approval transfers.

Fingerprints bind the discovered source/configuration files, effective analysis settings, analyzer release and recorded parser/coverage information. They exclude checkout roots and branding settings. They are not a complete installed-dependency/environment lock, a signed repository identity, or a whole-program semantic proof. Dynamic and unresolved callers remain uncertain.

Old inventories remain comparable, but missing v1.1 identity metadata invalidates assumptions needed to prove removal. `--allow-repository-mismatch` permits a deliberate comparison of different displayed repository names; it does not authenticate repository lineage. No semantic reviews, prices, timings, treatment results or activations are automatically copied into the new scan.

## 2. Rubric lint and bounded robustness probes

Create an event JSON with `state`, `questions`, `primary_question`, a pinned `model`, and optional `ground_truth`. `questions` uses the same typed API contract as the existing replay command. Every label must remain bound to its registered criterion; inspect instructions that refer to labels by name before interpreting renaming probes.

```bash
python -m jev_integration_evaluator rubric-lint --input questions.json --out lint.json
python -m jev_integration_evaluator robustness-plan --input event.json --out probe-suite.json
python -m jev_integration_evaluator robustness-run \
  --plan probe-suite.json --fixtures ordered-fixtures.json --out probe-results.json
python -m jev_integration_evaluator robustness-report \
  --plan probe-suite.json --input recorded-probes.json --out probe-analysis.json
```

The linter flags vague global judgments, duplicate questions, identical criterion text, missing explicitly named abstention choices and polarity-bearing labels. These deterministic flags are review leads; absence of warnings is not a semantic endorsement.

The suite contains exactly five probes: original, test–retest, reversed option order, opaque labels, and rotated label-to-criterion bindings. Criterion bodies and other question content must remain unchanged. Responses are normalized through the recorded bijective label mapping. The report includes disagreement, probability-distribution movement, correctness only when labels are supplied, provider confidence, usage and request/response hashes. Every failed or invalid probe remains in the schedule.

Order is included explicitly in request/cache identities. Legacy `FixtureClient` keys remain the default for old replay files; use `order_sensitive=True` for robustness fixtures. The original and retest intentionally share a request identity but are called separately. HTTP payloads preserve insertion order.

To deliberately make remote probes, replace `--fixtures` with `--allow-network`, set `TYPESAFE_API_KEY`, and provide both `--cost-upper-bound-per-call` and an adequate `--max-total-cost`. All five calls must fit the declared budget before the first request. `--max-calls` must also cover the complete schedule. Actual billed cost remains unknown unless independently measured; a declared upper bound is not a provider guarantee. Timeouts do not make a billed request free. No automatic retry or host action occurs.

Five probes on one state are a diagnostic, not a population benchmark, jailbreak certificate, or observed counterfactual task result. Agreement can be consistently wrong; ties and sampling variation need interpretation. Offline fixtures cannot establish live behavior.

## 3. Choose, freeze, then validate thresholds

`calibrate --select-threshold` remains a calibration-data exploration tool. Its adaptive selection result is not a holdout certificate. Freeze the actual chosen gate before evaluating an untouched test cohort:

```bash
python -m jev_integration_evaluator threshold-freeze \
  --input calibration-observations.jsonl --spec threshold-spec.json \
  --out frozen-threshold.json
python -m jev_integration_evaluator threshold-check \
  --input untouched-holdout.jsonl --plan frozen-threshold.json \
  --expected-digest RETAINED_POLICY_DIGEST --out holdout-report.json --enforce
```

`threshold-check` also writes `holdout-report.report.md`. Without `--enforce`, a successfully computed report exits 0 even when the evidence is insufficient: read its status. With `--enforce`, exit 3 means the gate is not supported by passing observed evidence; invalid inputs exit 2. Synthetic evidence always fails activation enforcement, even when numerical bounds pass.

Each labeled Choice observation requires `observation_id`, `task_hash`, `cluster_id`, `subgroup`, `kind: choice`, `split: calibration|test`, `model_id`, `policy_version`, `rubric_hash`, `evidence_type`, `probabilities`, explicit `choice`, `confidence` and ground-truth `label`. Use source-derived task/rubric hashes. All examples label their fabricated observations `synthetic`.

The threshold specification freezes global probability/confidence floors, optional per-action probability floors, abstention labels, maximum accepted-decision error, alpha, minimum accepted count, required subgroups and exact held-out observation identities. An action-specific probability floor is combined with the global floor using `max`.

Calibration and holdout may not share observation IDs, task hashes or cluster IDs. The test schedule requires one observation per task hash and cluster. Repeated episodes or correlated decisions cannot be relabeled as independent trials. A missing failed evaluation prevents validation; it cannot be silently omitted to improve the result. This gate currently expects complete labeled Choice observations, not a partial-response estimator.

For each frozen pooled/subgroup check the implementation computes a one-sided exact binomial error upper bound. Alpha is divided across the pooled check and prespecified subgroups. Every check must have enough accepted independent observations and an upper bound within the frozen risk limit. Zero accepted observations produce an unknown bound and fail. Small error-free samples can still fail because the bound remains too wide.

This calculation assumes independent, representative Bernoulli errors among accepted decisions. Unique IDs do not prove those assumptions. The guarantee does not extend to changed rubrics, shifted populations, different thresholds, adaptive holdout reuse, host inspection/fallback paths or deterministic security checks. Provider confidence is a distribution statistic used as a gate, not an asserted correctness probability.

## 4. Freeze the downstream task study

The old scan-generated `experiment-plan.json` is a design artifact, not a ready-made frozen study specification. Fill the `study-spec` schema with actual task identities, treatment versions and operational metrics. `templates/study-spec.example.json` is a deliberately synthetic contract example, not evidence.

```bash
python -m jev_integration_evaluator study-freeze \
  --spec study-spec.json --config analysis-config.yaml --out frozen-study.json
python -m jev_integration_evaluator study-check \
  --plan frozen-study.json --baseline baseline.jsonl --jev jev.jsonl \
  --expected-digest RETAINED_STUDY_DIGEST --out study-check.json
python -m jev_integration_evaluator study-evaluate \
  --plan frozen-study.json --baseline baseline.jsonl --jev jev.jsonl \
  --expected-digest RETAINED_STUDY_DIGEST --holdout-report holdout-report.json \
  --out study-results.json
```

The schedule includes task ID/hash, replicate, cluster, split and optional seed. Development, calibration and test split identities are checked for overlap. The baseline/JEV arms freeze treatment, code revision, model ID, policy version, prompt hash and mode; the study also freezes dataset ID, experiment ID, evidence type, required operational metrics and the effective validation/constraint configuration.

Collected rows must carry the frozen `study_digest`, `experiment_id`, `split: test`, matching `cluster_id`, `evaluation_scope: task_success`, and explicit `run_status`. The allowed statuses are `completed`, `failed`, `timeout`, `cancelled`, and `not_run`; every noncompleted status must report success as false. Keep honest known operational metrics; do not invent cost or latency simply to satisfy the schema. If a required measurement is absent, the study remains incomplete.

Exact schedule matching catches tasks missing from both arms, which ordinary paired matching cannot detect. No outcome is imputed or silently dropped. Shadow decisions and decision-label accuracy are not downstream task outcomes. Replay counts as a task outcome only when the actual recorded isolated replay/episode was executed and scored, not when an alternative action was merely predicted.

To permit a `keep` disposition through this stricter path, include both `holdout_report_digest` and `holdout_binding` in the study specification before freezing it. The binding contains `model_id`, `policy_version`, `rubric_hash` and the frozen threshold `policy_digest`. Supplied report self-integrity, schema, numerical checks and identities must match; a boolean calibration flag is insufficient. This links one explicitly identified acceptance gate; multi-placement treatments still require independent review of every active gate and interactions.

`study-evaluate` retains the original paired uncertainty, rescues/regressions, Bayesian usefulness, resource and safety checks. Synthetic task outcomes cannot justify adoption. The fixed-schedule/one-confirmatory-analysis rule is recorded, not enforced by a trusted external experiment service: local files cannot prove that an analyst did not inspect or reuse outcomes. `keep` never authorizes deployment.

## 5. Runtime lifecycle and migration

Existing constructors keep backward compatibility. New code should use the generated adapter's `create_router` factory or explicitly enable strict receipt handling:

```python
from jev_integration_evaluator.runtime import SafeRouter, Thresholds

router = SafeRouter(
    client,
    runtime_config,  # Off by default in the shipped configuration.
    policy_version="reviewed-policy-version",
    thresholds=Thresholds(),
    action_thresholds={"publish": Thresholds(probability_floor=0.99, confidence_floor=0.95)},
    activation=independently_approved_receipt,
    require_expiring_activation=True,
)
# The host may latch off new and in-flight proposals:
router.suspend()
# Or revoke the retained activation and latch off:
router.revoke_activation()
router.close()
```

`publish` is an illustrative registered Choice label, not a newly granted capability. Overrides must name actual choices and cannot lower any global threshold. Bind them using `digest({label: asdict(thresholds), ...})` in `action_thresholds_hash`. Because the runtime also has evidence/inspection gates, a Choice acceptance holdout does not automatically certify the entire host policy.

Strict receipts require the original approval/model/policy/questions/threshold hashes and holdout evidence reference, plus a nonempty activation ID, observed-evidence classification, timezone-aware issue/expiry timestamps and `ordered_questions_hash = request_fingerprint(None, questions, model)`. An expired, future-issued, revoked or mismatched receipt falls back without a model call; authorization is rechecked before returning a completed assessment. Receipts are host assertions, not signed proof that their claims are true.

A suspended router does not automatically resume; construct a new reviewed instance. Suspension cannot undo an already returned proposal or cancel a request already sent to a provider. A trusted host still validates current state, permissions and action-specific approval at execution time. Thread/socket budgets are not hard real-time guarantees.

## 6. Audit checkpoints and release verification

Store the final audit hash and event count outside the mutable log. A valid hash-chain prefix otherwise looks internally consistent after suffix truncation:

```bash
python -m jev_integration_evaluator verify-log --input audit.jsonl \
  --expected-final-hash RETAINED_FINAL_HASH --expected-events 123 --out audit-verification.json
python scripts/validate_package.py --check-manifest
```

Checkpoints detect disagreement with the retained checkpoint, not writer identity. The package manifest check verifies the exact included file set and rejects added/missing files, duplicates and unsafe paths. A trusted externally retained ZIP digest or signature is still needed for authenticity. Rebuilding intentionally changes release evidence/manifest bytes; do not treat a regenerated manifest as independent verification of modified files.

## Fully offline example

```bash
python scripts/run_v11_demo.py --out ../jev-v11-demo
```

Use a new or empty output directory. The demo runs 19 CLI operations, produces two fixture snapshots and readable change review, validates 80 synthetic task pairs, freezes a 40-row calibration selection and a 120-row synthetic holdout, executes five fixture probes, and verifies a three-event audit checkpoint. Exit 3 from its synthetic activation gate is expected and asserted. It executes no target code, performs no network request and takes no host action. Unit tests separately exercise observed-evidence code branches with explicitly artificial unit fixtures; they are not live studies.

## v1.2 continuation

The workflows above remain valid for v1.1 artifacts. New combined-treatment studies should use the every-gate manifest, role-sensitive rubric hash and raw holdout bundle described in `operational-evidence-v1.2.md`. Newly generated adapters additionally require full-runtime-bound expiring receipts, and shared workflow budgets must use the same coordinator instance. Do not treat the legacy single-gate binding as sufficient evidence for every gate in a new combined treatment.
