# JEV Integration Evaluator 1.2.0

**CompleteTech LLC · Evidence-driven integration analysis and evaluation**

A reusable agent skill and Python command-line toolkit for deciding **where JEV is useful, where it is not, how to integrate it, and how to measure whether it earns its place**. It implements the supplied 47-part specification through source analyzers, A–M placement playbooks, transparent scoring, constrained optimization, typed assessment runtime, approved patch workflow, reports and research tools.

The skill, Python distribution, and console command are named `jev-integration-evaluator`. The Python module is `jev_integration_evaluator`.

The [executable implementation engineering prompt](references/executable-implementation-prompt.md) reviews the current adapter and patch tooling and specifies the source transformations, host wiring, and verification needed for automated implementations. It is a development specification; its proposed commands are not yet implemented.

The default is deliberately conservative: **read-only analysis; no network; runtime off; no target code execution; no automatic adoption**. An unfamiliar repository can produce “no justified integration set.” That is a successful result, not an error.

## New in 1.2

| Improvement | Implemented behavior |
|---|---|
| Robust placement selection | Complete explicit scenarios; prerequisites/conflicts; worst-case utility, minimal sets and minimax regret; no unmeasured positive synergy. |
| Every-gate evidence | Current source review, exact question-role/rubric binding, recomputed raw holdouts for every gate, cross-stage leakage checks and allocated alpha budgets. |
| Shared workflow budgets | One atomic process-local ledger across placements; nonrefundable call/cost reservations, bounded concurrency, closed-task tombstones and overrun suspension. |
| Exact runtime approval | New factories bind the complete configuration, question roles, canary scope and shared limits to an expiring receipt; old approvals cannot silently authorize new exposure/settings. |
| Complete canary windows | Frozen task/arm/cohort schedules, honest unknowns, safety incidents retained in incomplete records, cost/latency/failure/fallback/action-mix limits and opt-in suspend-only host integration. |
| Runtime corrections | Copy request state/questions; cache only after successful audit and final checks; do not count cached inference tokens as new tokens. |

```bash
# From this extracted package; requires a new or empty output directory.
python scripts/run_v12_demo.py --out ../jev-v12-demo
```

The demonstration runs 17 CLI operations and makes zero network requests. Its two-gate study and monitoring outcomes are explicitly synthetic and cannot authorize adoption. See `references/operational-evidence-v1.2.md` for complete commands, input contracts, runtime examples and migration. Existing commands and v1.1 behavior remain supported; shared budgets are opt-in and require the same coordinator instance across participating routers.

## Retained from 1.1

| Improvement | What the running code now checks |
|---|---|
| Version-aware rescans | Source, configuration and analysis settings; changed boundaries/callers; no silent approval reuse. |
| Frozen downstream studies | Full task schedule, split leakage, exact treatment identity and required metrics, including failures missing from both arms. |
| Held-out acceptance risk | Frozen per-label floors, untouched holdout identities, exact error upper limits, subgroup checks and a synthetic-evidence block. |
| Rubric robustness | Five original/retest/order/label-binding probes with order-aware request/cache identity and explicit failed-probe accounting. |
| Runtime lifecycle | Stricter per-action gates, expiring receipts, revocation and in-flight suspension checks; strict factories for newly generated adapters. |
| Evidence integrity | Audit-head/length checkpoints and exact release file-set validation. |

See `CHANGELOG.md` and `references/lifecycle-and-evidence.md` for the implementation, new commands, assumptions and compatibility details. No live model benefit is claimed.

## Get started

Requires Python 3.10 or newer. Runtime dependencies are PyYAML and jsonschema. NumPy, SciPy and a model API are **not** required for the analysis/statistical commands. Optional reliability-chart output needs matplotlib. For native JavaScript/TypeScript analysis, install trusted Node tooling and TypeScript 5.x or 6.x; the development toolchain is pinned in `package.json` and does not load target-repository plugins.

```bash
# Run only after approving dependency installation in your environment.
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[test]"

# Optional trusted TypeScript parser, installed here rather than in the target.
npm install --ignore-scripts --no-audit --no-fund

# Local analysis; use an output directory outside the target for clean repeated scans.
python -m jev_integration_evaluator scan --repo /path/to/repo --out ./analysis --depth STANDARD
python -m jev_integration_evaluator onboard --inventory ./analysis/jev-opportunities.json
```

The installed console command `jev-integration-evaluator` is equivalent to `python -m jev_integration_evaluator`. A PowerShell path with spaces must be quoted. WSL shutdown, branch publication, merge and deployment are never part of the default workflow.

## Run the entirely offline demonstration

From the extracted skill directory after installing its Python dependencies:

```bash
python -m jev_integration_evaluator scan --repo examples/coding-agent --out demo/agent
python -m jev_integration_evaluator scan --repo examples/generic-service --out demo/deterministic
python examples/run_demo.py --out demo/runtime
python -m jev_integration_evaluator replay --input examples/research/decisions.jsonl --fixtures examples/research/fixture-responses.json --out demo/replay.json
python -m jev_integration_evaluator compare --baseline examples/research/baseline.jsonl --jev examples/research/router-verifier.jsonl --out demo/results.json
python -m jev_integration_evaluator calibrate --input examples/research/calibration-test.jsonl --out demo/calibration.json
python -m jev_integration_evaluator ablate --baseline examples/research/baseline.jsonl --variants examples/research/variants.json --out demo/ablations.json
python -m pytest -q
python scripts/validate_package.py
```

**Every model response and study outcome in `examples/research` is synthetic.** The examples establish that the tools execute and check contracts; they do not establish a live-model improvement. Synthetic results cannot produce a keep recommendation. The original runtime demonstration proposes a typed action but executes zero actions and makes zero remote requests. The v1.2 runtime demonstration is shadow-only and returns baseline proposals.

## Run the v1.1 lifecycle demonstration

```bash
# Requires a new or empty output directory. All model/study responses are synthetic.
python scripts/run_v11_demo.py --out ../jev-v11-demo
```

The demo exercises 19 CLI operations: rescan/diff, frozen paired study, frozen held-out threshold validation, five robustness probes, and audit checkpoints. It explicitly verifies that synthetic holdout results cannot qualify for activation. `diff` and `threshold-check` emit readable `.report.md` sidecars beside their JSON results.

```bash
python -m jev_integration_evaluator diff --before previous/jev-opportunities.json \
  --after current/jev-opportunities.json --out change-review.json
python -m jev_integration_evaluator study-freeze --spec study-spec.json --out frozen-study.json
python -m jev_integration_evaluator threshold-check --plan frozen-threshold.json \
  --input untouched-holdout.jsonl --out holdout-report.json --enforce
```

Use the reference guide to create genuine input contracts; the template/example identities are not production evidence. `--enforce` exits 3 when activation evidence is not supported, including every synthetic-only result.

## What is implemented

| Area | Working capability |
|---|---|
| Discovery | Python AST and optional native TypeScript compiler AST; calls, local assignment dataflow, branches, loops, exception paths, source hashes, conservative call/side-effect maps, 13 A–M patterns, deterministic/generative rejection. Other languages retain explicit review-only leads. |
| Design | Atomic, bounded Choice/Noul rubrics, typed Score contract support, legal-action membership, evidence requirements, baseline fallback, timing/bypass and deterministic policy recommendations. |
| Ranking | All 16 configured weighted dimensions, explanations and unknown intervals; hard rejection gates; source-matched semantic reviews; source-correlated runtime measurements. |
| Placement selection | Minimal, balanced and maximum-reliability sets under latency, cost, calls, complexity, risk and throughput constraints. Conflicts and measured interaction effects; exact small-set search and explicitly approximate larger-set search. |
| Evaluation | Strict paired task/replicate matching, rescues/regressions, exact McNemar where appropriate, clustered bootstrap, paired Bayesian useful-effect analysis, effect sizes, p50/p95 latency, efficiency, Pareto fronts, failure transitions, economic break-even and ablations. |
| Runtime | Default-off, nonblocking bounded shadow work, task-level canary assignment, explicit activation receipt, separate probability/confidence thresholds, budgets, timeouts, circuit breaker, immutable state-scoped cache, hash-chained redacted logs. |
| Implementation | Executable adapter scaffold, optional authorized worktree creation, exact-content diff plan and digest-approved local apply, stale-source guards, authorized test command runner, source-to-implementation/test/outcome receipt links. |
| Delivery | Six Markdown reports, JSON/CSV inventory, effective YAML configuration, architecture/experiment/optimization JSON, optional Mermaid and calibration plot, examples, JSON schemas and tests. |

## Output files

A scan writes `JEV_OPPORTUNITIES.md`, `JEV_ARCHITECTURE.md`, `JEV_INTEGRATION_PLAN.md`, `JEV_EXPERIMENT_PLAN.md`, `JEV_RISK_ANALYSIS.md`, `JEV_RESULTS.md`, `jev-opportunities.json`, `jev-opportunities.csv` and `jev-config.yaml`. It also writes `architecture.json`, `architecture.mmd`, `experiment-plan.json` and `jev-placement-sets.json`.

The initial results report explicitly says no experiment was run. Supply a real comparison result to `report --results results.json` to include measured outcomes. Scores and optimizer estimates are never presented as observed model performance.

## Agent installation

Copy this entire directory into an agent's explicitly configured skill directory; keep `SKILL.md`, the Python package, schemas and references together. Agent runners with skill discovery can read the frontmatter and follow the staged workflow; runners without discovery can be directed to read `SKILL.md` and invoke the CLI. No runner configuration is modified by this package. Install the Python package in the execution environment separately when invoking it outside the skill directory.

`ONBOARDING.md` defines progressive intake. `AGENTS.md` defines contributor and execution boundaries. `BRANDING.md` explains the disclosed CompleteTech text-only starter, customer overrides and unbranded mode. No proprietary logo or font is bundled, and the package does not claim TypeSafe affiliation.

## Live JEV integration

The HTTP adapter follows the official `/v1/systemone` structured-question API and pins `jev-1.13.0` by default. See the dated primary-source record in `references/sources.md` and reverify the contract before changing the pin. Noul is a yes-probability, Choice/Score confidence is a distinct provider statistic, and neither proves that host policy should authorize an action.

No key is needed for local scans or the offline fixtures. To deliberately transmit approved, minimized evidence, set `TYPESAFE_API_KEY` in the process environment and explicitly authorize network egress. Remote replay additionally requires a conservative cost-per-call bound and total budget. No current price is silently assumed.

```bash
# This transmits approved decision states; do not use raw production secrets.
python -m jev_integration_evaluator replay --input approved-decisions.jsonl --allow-network \
  --max-calls 5 --max-total-cost 0.01 --cost-upper-bound-per-call 0.002 \
  --out approved-replay-results.json
```

Newly generated adapters require an expiring receipt bound to the exact model, rubric, question roles, full runtime configuration, thresholds, canary scope and shared-budget limits, with independently validated held-out evidence. Existing direct constructors retain legacy defaults for compatibility. New scaffold factories also require issue/expiry timestamps and order-sensitive rubric identity; legacy direct constructors retain optional migration. The scaffold does **not** guess a correct host rewrite: an authorized agent must inspect the actual call site, map typed labels to existing behavior, add tests and apply the reviewed diff. See `references/integration-playbook.md`.

## Support boundaries

Static analysis cannot recover every reflective/dynamic call, macro, callback, generated source or deployment effect. The Python parser includes module-level statements; native JavaScript/TypeScript analysis focuses on function, method and arrow scopes. Unsupported-language and unavailable-parser results are review-only. Do not treat a partial scan as proof that a repository has no opportunities.

A socket timeout and bounded thread pool are not hard real-time guarantees. The test runner is not a security sandbox; use an isolated runner for untrusted projects. Externally retained hash/length checkpoints detect mismatching audit prefixes, but hash chains do not authenticate an adversarial writer. Frozen local manifests cannot prove an untouched holdout or independent trials; their statistical assumptions remain explicit. API fixtures and receipts can be forged by an untrusted editor; authorization and independent experiment review remain host responsibilities.

Validation results for this package are in `validation/VALIDATION.md`. Live JEV accuracy, cost, latency and calibration were not measured during package construction. The tested model interface uses mocked HTTP and exact local fixtures.

## License

Code and authored documentation are MIT licensed. Names and marks are not transferred by the code license. The user-supplied specification is retained as provenance, not relicensed as a third-party brand asset. See `LICENSE` and `BRANDING.md`.
