# JEV Integration Evaluator 1.3.0.dev7

**CompleteTech LLC · Evidence-driven integration analysis and evaluation**

A reusable agent skill and Python command-line toolkit for deciding **where JEV is useful, where it is not, how to integrate it, and how to measure whether it earns its place**. It implements the supplied 47-part specification through source analyzers, A–M placement playbooks, transparent scoring, constrained optimization, typed assessment runtime, approved patch workflow, reports and research tools.

The skill, Python distribution, and console command are named `jev-integration-evaluator`. The Python module is `jev_integration_evaluator`.

The [original executable implementation specification](references/executable-implementation-prompt.md) is retained as requirements provenance. The supported commands and deliberately bounded implementation coverage in this development build are documented in [the current support contract](references/executable-integrations.md).

The default is deliberately conservative: **read-only analysis; no network; runtime off; no target code execution; no automatic adoption**. An unfamiliar repository can produce “no justified integration set.” That is a successful result, not an error.

## Experimental selection in 1.3.0.dev7

The [placement selection contract](references/experimental-selection.md) can
select a source-matched, semantically reviewed candidate for bounded **plan
preparation** even when benefit and cost estimates are unknown. It keeps
estimate-based optimization separate and reports why a candidate was rejected,
needs review, lacks estimates, or is unsupported by the current implementation
recipes. Use `python -m jev_integration_evaluator.selection` with a private
reviewed envelope; the exact request requires external approval before
preparation. Selection does not execute target code, authorize live spend or
activation, or establish measured benefit. [Current validation](validation/SELECTION-VALIDATION-1.3.0.dev7.md)
uses synthetic host wiring. Issue #7 and the broader repository command remain
open.

## Review exclusions in 1.3.0.dev6

Semantic reviews now retain deterministic and hard-real-time exclusions. A
review cannot clear a hard-real-time flag or downgrade a preferred/mandatory
deterministic alternative. The whole review batch is validated before the
inventory changes, and duplicate candidate IDs are rejected. Successful review
preserves existing candidate references used by later trace analysis. See
[the review boundary](references/review-gate-invariants.md) and
[dev6 validation](validation/REVIEW-GATE-VALIDATION-1.3.0.dev6.md).

## Source-bound discovery and semantic review in 1.3.0.dev5

The `repository-discovery` command builds the existing inventory from current
Python source and accepts a separately authored semantic review. Opaque symbols
can be nominated without renaming source or inventing inventory entries.
Preparation and review recheck source, policy, parser and engine identity.
Deterministic and hard-real-time exclusions apply to every generated candidate.

```bash
python -m jev_integration_evaluator repository-discovery TARGET --out NEW_EXTERNAL_REPORT.json
python -m jev_integration_evaluator repository-discovery TARGET --stage prepare --capabilities REPORT.json --nominations NOMINATIONS.json --out NEW_EXTERNAL_PREPARED.json
python -m jev_integration_evaluator repository-discovery TARGET --stage review --capabilities REPORT.json --prepared PREPARED.json --review SEMANTIC_REVIEW.json --out NEW_EXTERNAL_REVIEWED.json
python -I scripts/run_capability_demo.py --out NEW_PRIVATE_DIRECTORY
```

Read [the stage contracts](references/repository-discovery-v1.md) for exact input,
external policy, private output and review requirements. Existing
`discover-capabilities` and `nominate-candidate` commands retain their
[published contracts](references/capabilities.md). New stages use the same
discovery engine. Native Windows discovery is unsupported; JS/TS coverage in this
command remains explicitly incomplete.

This is a partial delivery for [issue #5](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/5).
A complete source-reviewed no-useful-placement outcome and the repository
implementation session remain outstanding. A semantic opinion supplies neither
host bindings nor execution/activation authority. Current qualification is in
[the dev5 validation record](validation/SEMANTIC-BRIDGE-VALIDATION-1.3.0.dev5.md).

## Executable integrations retained from 1.3.0.dev3

This development build implements **A–M Python host transformations** for the explicitly bounded `module-tail-call-v1` source shape. A strict source-matched binding spec drives generated host edits, default-off runtime wiring, exact reviewed apply, actual host-entry verification, externally anchored status and owned-byte rollback. It does not ask the caller to write the replacement function. The thirteen synthetic examples and the complete CLI demo exercise the edited hosts, not just adapter methods.

```bash
python -m jev_integration_evaluator implementation-recipes --json
python scripts/run_implementation_demo.py --out ../jev-implementation-demo
```

Read [the executable support matrix and lifecycle](references/executable-integrations.md) before using a recipe. It documents mandatory existing host bindings, the strict source/registry shapes, the exact CLI flags, local receipt trust boundaries, interrupted recovery and limits. `examples/implementation/` contains real source-matched binding examples. Analysis and plan/status commands do not execute target code. Mutation and host verification require their distinct scopes.

The verifier demonstrates **synthetic host wiring**, not application benefit or production activation. Its test runtime is deliberately injected; it does not certify a real provider/bootstrap. Unsupported Python shapes are rejected before mutation; JavaScript/TypeScript remain analysis-only. No Node runtime is needed for Python rewriting. Earlier v1.1/v1.2 validation remains historical evidence, not a claim about this development build.

## Failure-accounting and source fidelity in 1.3.0.dev3

Probe observations now have a strict, mirrored contract. Null, incomplete, malformed or out-of-bound observations cannot pass a baseline, establish host wiring or erase scheduled failures. Missing authorized runners are recorded as `not_run`; a successful probe cannot substitute for a required command that did not execute. Receipt loading checks the complete ordered case/mode schedule, counts, observations and command identities against the reviewed specification.

Baseline and modified verification write durable start markers before execution. If the process is interrupted, status reports `blocked_recovery`; an older passing baseline cannot authorize apply after that interrupted attempt. Fresh authorized verification or an exact owned-byte rollback can recover. Command status must agree with its exit code, and receipt output stays within the reader's size limit while retaining every scheduled case. UTF-8 source cookies are validated before transformation, and generated imports stay outside unrelated decorated definitions, including multiline decorators. Decorated **selected seams** and non-UTF-8 source remain unsupported.

The [dev3 validation record](validation/SAFETY-VALIDATION-1.3.0.dev3.md) is retained as historical evidence alongside dev1/dev2 and v1.1/v1.2 validation. This release adds no live activation path, new runtime dependency or broader rewriting claim.

## Retained safety follow-up from 1.3.0.dev2

Host-owned exceptions are never model routing instructions: after an executor, finisher or completed-result callback starts, fallback cannot replay it. Runtime/coordinator ownership tombstones survive garbage collection, so constructing replacements cannot reset a workflow's charged work. Parameter shadowing and Python exception/match captures are rejected before mutation when they make bindings ambiguous.

Every verification copy must match the reviewed phase bytes and modes. A final check includes the generated adapter, including after an authorized command exits successfully. New receipts expose `file_identity_valid`; this field is evidence metadata, never execution or activation authority. The support matrix and CLI remain bounded and unchanged. The historical dev2 results remain in `validation/SAFETY-VALIDATION-1.3.0.dev2.md`; current qualification is recorded separately.

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

Newly generated adapters require an expiring receipt bound to the exact model, rubric, question roles, full runtime configuration, thresholds, canary scope and shared-budget limits, with independently validated held-out evidence. Existing direct constructors retain legacy defaults for compatibility. New scaffold factories also require issue/expiry timestamps and order-sensitive rubric identity; legacy direct constructors retain optional migration. The legacy `scaffold` command remains a proposal-adapter generator. For a supported, reviewed source shape, use `implement-plan` to derive the actual call-site edit and run the connected lifecycle. Unsupported shapes require separate implementation, not an automatic broad textual replacement. See `references/executable-integrations.md` and `references/integration-playbook.md`.

## Support boundaries

Static analysis cannot recover every reflective/dynamic call, macro, callback, generated source or deployment effect. The Python parser includes module-level statements; native JavaScript/TypeScript analysis focuses on function, method and arrow scopes. Unsupported-language and unavailable-parser results are review-only. Do not treat a partial scan as proof that a repository has no opportunities.

A socket timeout and bounded thread pool are not hard real-time guarantees. The test runner is not a security sandbox; use an isolated runner for untrusted projects. Externally retained hash/length checkpoints detect mismatching audit prefixes, but hash chains do not authenticate an adversarial writer. Frozen local manifests cannot prove an untouched holdout or independent trials; their statistical assumptions remain explicit. API fixtures and receipts can be forged by an untrusted editor; authorization and independent experiment review remain host responsibilities.

Development validation is in [the dev6 review-gate report](validation/REVIEW-GATE-VALIDATION-1.3.0.dev6.md), with supplied-fragment and full integration qualification distinguished. Earlier v1.1, v1.2 and dev1–dev5 validation records are retained byte-for-byte as historical evidence; they are not measurements for this build. Live JEV accuracy, cost, latency and calibration were not measured during package construction. The tested model interface uses mocked HTTP and exact local fixtures.

## License

Code and authored documentation are MIT licensed. Names and marks are not transferred by the code license. The user-supplied specification is retained as provenance, not relicensed as a third-party brand asset. See `LICENSE` and `BRANDING.md`.
