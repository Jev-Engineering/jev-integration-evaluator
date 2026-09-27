# Requirements-to-implementation traceability

The user-supplied 47 numbered sections are retained in `requirements-source.txt`. This matrix points to working components, not a claim that any live JEV deployment has been validated. Module paths are under `jev_integration_evaluator/`; reference filenames are under `references/`; test paths are under `tests/`.

| Section | Requirement | Implementation | Validation evidence |
|---:|---|---|---|
| 1 | Placement score | `scoring.py; config.py` | `test_scanner.py; test_inputs_optimizer.py` |
| 2 | Semantic boundaries | `scanner.py` | `test_scanner.py` |
| 3 | A–M strongest patterns | `patterns.py; scanner.py` | `test_scanner.py` |
| 4 | Deterministic anti-patterns | `scanner.py; scoring.py` | `test_scanner.py` |
| 5 | Avoid unnecessary generation | `scanner.py; anti-patterns.md` | `test_scanner.py` |
| 6 | Atomic questions | `questions.py; patterns.py` | `test_scanner.py` |
| 7 | Bounded choices | `questions.py; client.py` | `test_runtime_client.py` |
| 8 | Confidence affects behavior | `runtime.py; calibration.py` | `test_runtime_client.py` |
| 9 | Assessment versus policy | `runtime.py; integration-playbook.md` | `test_runtime_client.py` |
| 10 | Downstream leverage | `scanner.py; scoring.py` | `test_scanner.py` |
| 11 | Long-horizon reliability | `statistics.py:long_horizon` | `test_statistics.py` |
| 12 | Opportunity inventory | `scanner.py; reports.py` | `test_implementation_schemas_cli.py` |
| 13 | Ranked plan | `scoring.py; reports.py` | `test_scanner.py` |
| 14 | Placement interactions | `scanner.py; optimizer.py` | `test_inputs_optimizer.py` |
| 15 | Placement optimizer | `optimizer.py` | `test_inputs_optimizer.py` |
| 16 | Experimental framework | `statistics.py; experiment template` | `test_statistics.py` |
| 17 | Rescues/regressions | `statistics.py` | `test_statistics.py` |
| 18 | Effects and uncertainty | `statistics.py` | `test_statistics.py` |
| 19 | Bayesian usefulness | `statistics.py:bayesian_paired` | `test_statistics.py` |
| 20 | Pareto analysis | `optimizer.py:pareto_front` | `test_inputs_optimizer.py` |
| 21 | Break-even economics | `statistics.py:economics` | `test_statistics.py` |
| 22 | Inference efficiency | `statistics.py:compare_runs` | `test_statistics.py` |
| 23 | Failure transitions | `statistics.py:failure_transitions` | `test_statistics.py` |
| 24 | Staged workflow | `SKILL.md; cli.py` | `test_implementation_schemas_cli.py` |
| 25 | Search strategy | `scanner.py; architecture-analysis.md` | `test_scanner.py` |
| 26 | Runtime trace correlation | `traces.py` | `test_implementation_schemas_cli.py` |
| 27 | Offline replay | `replay.py; client.py` | `test_runtime_client.py` |
| 28 | Shadow mode | `runtime.py` | `test_runtime_client.py` |
| 29 | Canary/rollback | `runtime.py` | `test_runtime_client.py` |
| 30 | Configuration | `config.py; config schema` | `test_inputs_optimizer.py` |
| 31 | Output artifacts | `reports.py` | `test_implementation_schemas_cli.py` |
| 32 | Primary report | `reports.py` | `test_implementation_schemas_cli.py` |
| 33 | Implementation mode | `implementation.py; integration-playbook.md` | `test_implementation_schemas_cli.py` |
| 34 | Safety/reversibility | `runtime.py; implementation.py` | `test_runtime_client.py; test_implementation_schemas_cli.py` |
| 35 | Caching | `runtime.py; traces.py` | `test_runtime_client.py` |
| 36 | Calibration | `calibration.py` | `test_statistics.py` |
| 37 | Ablations | `statistics.py:ablation_analysis` | `test_statistics.py` |
| 38 | Stop criteria | `statistics.py; scoring.py` | `test_statistics.py; test_scanner.py` |
| 39 | Skill package | `SKILL.md; schemas/scripts/references/templates/examples/tests` | `validate_package.py` |
| 40 | Onboarding | `onboarding.py; ONBOARDING.md` | `test_traceability_onboarding.py` |
| 41 | Progressive depth | `config.py; scanner.py; SKILL.md` | `test_scanner.py; test_inputs_optimizer.py` |
| 42 | Explainability | `scoring.py; reports.py` | `test_scanner.py` |
| 43 | Traceability | `scanner.py; traceability.py; runtime.py` | `test_traceability_onboarding.py` |
| 44 | Architecture philosophy | `SKILL.md; runtime.py` | `test_runtime_client.py` |
| 45 | Selective target architecture | `patterns.py; optimizer.py` | `test_inputs_optimizer.py` |
| 46 | Definition of success | `reports.py; full CLI workflow` | `test_implementation_schemas_cli.py` |
| 47 | Acceptance and execution | `all modules; validation/VALIDATION.md` | `full test suite; offline/third-party smoke checks` |

## Boundaries that remain explicit

The autonomous agent performs source-specific semantic review and host-callsite wiring using the supplied tools; the scanner is not a whole-program semantic proof and the scaffold does not automatically rewrite arbitrary hosts. Native AST support covers Python and optional JavaScript/TypeScript; other languages need explicit source review. Implementation/testing, egress and deployment remain separate approvals.

The package ships executable research analysis, but no live JEV effectiveness, production calibration, monetary saving or end-to-end performance claim. Synthetic fixtures cannot satisfy adoption. Offline unit tests exercise the documented API contract with mock HTTP; operators must run approved live evaluation and independent held-out calibration for their actual task distribution.

## v1.1 extension traceability

| Original sections | Implemented extension | Code | Tests |
|---|---|---|---|
| 24–26, 42–43 | Version-aware source/configuration fingerprints, conservative rescan comparison and readable impact report | `scanner.py`, `lifecycle.py` | `test_lifecycle_v11.py`, `test_cli_v11.py` |
| 14, 16–19, 28–29, 37–38 | Frozen paired schedules, split/treatment binding, complete failure denominator, downstream-task scope guard | `study.py`, `statistics.py` | `test_study_v11.py` |
| 8, 18, 36 | Frozen acceptance policy, disjoint complete holdout, exact/subgroup risk checks and report validation | `holdout.py`, six v1.1 schemas | `test_holdout_v11.py` |
| 6–7, 34, 36, 42 | Atomic-question lint and label/order invariance probes | `robustness.py`, `client.py` | `test_robustness_v11.py` |
| 8–9, 29, 33–35 | Per-action thresholds, strict factory, expiring receipts, suspension/revocation, ordered cache identity | `runtime.py`, `implementation.py` | `test_runtime_v11.py`, existing adapter tests |
| 34, 43, 47 | Externally pinned audit head/length and exact release file-set checks | `traces.py`, `scripts/validate_package.py` | Runtime checkpoint tests and release-validation checks |
| 31, 39–41, 47 | Runnable offline lifecycle, compatible templates, readable reports and expanded skill instructions | `scripts/run_v11_demo.py`, `references/lifecycle-and-evidence.md`, `SKILL.md` | `test_cli_v11.py` |

This extends, rather than replaces, the original section-by-section map. No score, synthetic fixture, label-invariance result or holdout-bound calculation is itself permission to execute a host action.

## v1.2 extension traceability

| Original sections | Implemented improvement | Code / commands | Tests |
|---|---|---|---|
| 14–15, 20–21, 38, 42 | Explicit scenario sensitivity, common feasible sets, worst-case and regret decisions, prerequisite/conflict constraints | `scenarios.py`, `optimize-robust` | `test_scenarios_v12.py` |
| 8, 14, 16–19, 36–37, 43 | Every source/role-bound gate, recomputed raw holdouts, alpha allocation, cross-stage leakage, complete combined-treatment study | `gates.py`, `study.py`, study commands | `test_gates_v12.py` |
| 15, 28–30, 34–35 | Shared task/lifetime/concurrency accounting; no refunds or tombstone resets; exact-runtime receipts | `budget.py`, `runtime.py`, `implementation.py` | `test_budget_runtime_v12.py` |
| 23, 26, 29, 34, 38 | Complete cohort-aware fixed windows; unknown metrics, safety incidents, drift, expiry and suspend-only host hook | `monitoring.py`, `cohorts.py`, monitor commands | `test_monitoring_v12.py` |
| 22, 26, 35 | Cached tokens do not count as new inference; unaudited responses not cached | `traces.py`, `runtime.py` | `test_cli_v12.py`, `test_budget_runtime_v12.py` |
| 31, 33, 39–41, 47 | Six new schemas, new input templates, strict factory, executable offline end-to-end example and migration | `scripts/run_v12_demo.py`, `references/operational-evidence-v1.2.md`, `SKILL.md` | `test_cli_v12.py`, package validator |


## Executable-integration implementation requirements (development)

| Requirement | Executable components | Evidence/limits |
|---|---|---|
| Strict source-matched binding, review, candidate/experiment and AST anchor | `integrations/contracts.py`, `integrations/recipes.py`; implementation spec/schema copies | `test_executable_safety.py`; no imports during scan/plan; unsupported shapes rejected |
| A–M pattern-specific host transformations | `integrations/recipes.py`, `integrations/host.py` | `test_executable_recipes.py`; all thirteen execute actual modified host entry points |
| Explicit semantic labels, unchanged legacy receipts and shared runtime budgets | `runtime.py` optional label translation; strict generated factories | Existing runtime tests plus `test_executable_runtime.py`; no new activation bypass |
| Exact bundle/apply/status and durable recovery | `integrations/lifecycle.py`; existing protected patch engine | `test_executable_safety.py`; exceptions, actual process termination, drift, owned-byte rollback and tampering |
| Independent synthetic host verification and receipt trust | `integrations/probe.py`, `integrations/verification.py` | Always-true postcondition negative; observed call/effect traces; external receipt digest required for later certified status |
| Actual commands, scripts and offline demo | `cli.py`, `scripts/implement_*.py`, `scripts/implementation_recipes.py`, `scripts/run_implementation_demo.py` | `test_executable_cli.py`; nonzero failure/blocked exits, complete CLI lifecycle |
| Installation, strict data discovery and release parity | Packaged implementation schemas and factory imports | `test_executable_wheel.py`, `validate_package.py`; installed-wheel host lifecycle |
| Synthetic source-matched specifications | `examples/implementation/a` through `m` and `implementation_fixtures.py` | Real scans/reviews; no final replacement function supplied by caller |
| Support/activation boundaries | `references/executable-integrations.md` | Flat Python modules and explicit registries only; synthetic tests, not live/provider/bootstrap/benefit certification; JS/TS rewriting unsupported |

Repository publication, signed commits, external review/CI and merge are delivery actions, not capabilities inferred from a local plan or test receipt. Consult the current delivery report for actions actually performed.
