# Engineering prompt: executable JEV integrations

**Historical specification:** This prompt describes the planned Python delivery
at reviewed baseline `1cca65a0`. Its future-tense and JS/TS analysis-only
statements are preserved as requirements history, not current support status.
For delivered bounds see [Python executable integrations](executable-integrations.md),
[JS/TS recipe C](javascript-typescript-backend-v1.md),
[Python adaptation](python-adaptation-v1.md), and
[bounded composite transactions](composite-transactions-v1.md).

Status: reviewed implementation specification. The new commands and artifacts below are requirements for future code, not capabilities already shipped by this document.

Reviewed baseline: `1cca65a06d36aa52d77bf28c595b1569a72066f6`. Recheck the actual checkout before making changes. All paths in this document are relative to the repository root.

## Task

Extend JEV Integration Evaluator so its scripts can implement selected JEV integrations in a target repository. Deliver working source transformations, host wiring, executable verification, and reproducible evidence. A user must be able to go from a reviewed opportunity and an explicit binding specification to a reviewed patch, an applied integration, and independently checked host behavior.

Do not stop after generating a proposal adapter, writing wiring instructions, or asking the caller to author the complete replacement source in `changes.json`. The implementation engine must produce the host edits for supported source shapes. Preserve explicit unsupported results for source shapes it cannot implement correctly.

Keep the public names `jev-integration-evaluator` and `jev_integration_evaluator`; do not restore the removed naming aliases. Keep existing command and receipt semantics unless a separately documented migration is necessary. Use the current runtime, budgets, evidence gates, and patch protections rather than building a parallel runtime.

## Review findings to verify first

Read `SKILL.md`, `AGENTS.md`, `CONTRIBUTING.md`, and the integration, architecture, lifecycle, and operational evidence references. Inspect the following code before designing extensions:

| Existing component | What it currently does | Missing implementation behavior |
|---|---|---|
| `jev_integration_evaluator/implementation.py::scaffold_integration` | Writes `adapter.py`, `test_adapter.py`, `integration-manifest.json`, and `WIRING.md`. Its manifest explicitly says the adapter is not connected to the host. | No target call-site transformation, caller update, dependency injection wiring, or proof that the host invokes the adapter. |
| `jev_integration_evaluator/implementation.py::make_patch_plan` | Hashes and displays exact changes supplied as complete `new_content` strings. | Does not derive those changes from a reviewed opportunity or a supported implementation recipe. |
| `jev_integration_evaluator/implementation.py::apply_patch_plan` | Applies an approved digest with path/hash checks and rollback attempts on write failure. | Does not establish semantic correctness, prove host wiring, or provide durable recovery after process interruption. |
| `jev_integration_evaluator/implementation.py::run_authorized_tests` | Runs an authorized argument vector, captures bounded output, and reports exit status. | Exit success alone does not prove the selected host path was exercised or the intended postcondition held. Environment filtering is explicitly not a sandbox. |
| `jev_integration_evaluator/cli.py` | Exposes `scaffold`, `patch-plan`, `apply`, `worktree`, `run-tests`, and `link`. | No connected implementation lifecycle driven by a validated binding specification. |
| `jev_integration_evaluator/runtime.py::SafeRouter` and `jev_integration_evaluator/questions.py` | Produce bounded assessments, enforce runtime policy, and validate selected labels against registered choices. | Different integration patterns need explicit mappings from assessment labels to host behavior. A semantic label such as `same` or `supports` is not inherently a tool name or execution grant. |
| `jev_integration_evaluator/traceability.py::link_artifact` | Links an artifact hash to a candidate, original source hash, and experiment. | An implementation manifest's assertions do not independently establish applied or verified wiring. |
| `tests/test_implementation_schemas_cli.py` | Exercises exact text patches and the generated adapter's default-off behavior. | Does not demonstrate automatic source edits followed by execution through a modified host entry point. |
| `examples/coding-agent`, `examples/rag-system`, and `examples/graph-system` | Supply injectable analysis fixtures with useful integration seams. | They are not production integrations. The graph fixture does not connect to a database. |

The current parser is a conservative source analyzer, not a complete control-flow proof or an existing rewrite engine. Python AST coverage and optional TypeScript AST coverage must not be presented as transformation coverage.

## Required user journey

1. Scan a target without importing or executing it. Select a candidate after source-matched semantic review; preserve a valid result that no integration is useful.
2. Choose a registered implementation recipe and provide the host bindings and behavioral objective that cannot be inferred safely. Read existing configuration and previously supplied answers before asking for anything again.
3. Validate current source identity, candidate eligibility, recipe support, bindings, runtime policy, and test scope. A tier number or placement score alone is insufficient.
4. Produce a complete implementation bundle outside the target. Include the host edits, adapter/configuration changes, tests, exact patch, and a plan explaining which source path will call the adapter. Planning must not change the target or execute target code.
5. Capture the authorized baseline checks before mutation, using appropriate isolation and exact source hashes. If execution authority is missing, retain the plan and report the missing scope without running target code.
6. Apply only the reviewed content digest within authorized scope, preferably in an isolated worktree. Existing session authorization can cover routine preparation; a model-generated digest is not itself permission to apply an unseen patch.
7. Execute the authorized modified-host checks and compare them with the preserved baseline. Verify postconditions and the modified call path, then record complete results.
8. Report whether the integration is planned, applied, verified, unsupported, blocked, failed, or rolled back. Runtime activation and evidence of application benefit remain separate decisions.

## Architecture and executable interfaces

Implement the orchestration in focused Python modules, with thin CLI and `scripts/` entry points. Refactor `implementation.py` where useful; do not duplicate its protected-path, exact-digest, source-drift, or atomic-write logic. Keep dependencies small and explain any new dependency.

A concrete suggested command surface is:

```text
jev-integration-evaluator implementation-recipes --json
jev-integration-evaluator implement-plan --repo TARGET --inventory REVIEWED --candidate ID --spec SPEC --out BUNDLE
jev-integration-evaluator implement-verify --phase baseline --repo TARGET --bundle BUNDLE --approve-execution --out BASELINE_RECEIPT
jev-integration-evaluator implement-apply --repo TARGET --bundle BUNDLE --approve REVIEWED_DIGEST
jev-integration-evaluator implement-verify --phase modified --repo TARGET --bundle BUNDLE --approve-execution --out RECEIPT
jev-integration-evaluator implement-status --repo TARGET --bundle BUNDLE
jev-integration-evaluator implement-rollback --repo TARGET --bundle BUNDLE --approve REVIEWED_ROLLBACK_DIGEST
```

These command names are proposed. Choose a consistent interface after inspecting the current parser, document the final interface, and exercise it through subprocess tests. Provide matching single-purpose scripts where that is the repository convention. Do not advertise the commands before they work.

### Binding specification

Define a versioned strict schema and real example specifications. Put identical schema copies in `schemas/` and `jev_integration_evaluator/data/`, and extend configuration validation, CLI `validate`, and package validation together.

The specification must identify:

- Candidate and experiment IDs, reviewed inventory fingerprint, current source hashes, qualified symbol, and an unambiguous statement/call anchor. Line numbers alone cannot identify a seam.
- Recipe ID/version and supported language/source shape. Record an explicit reason for unsupported syntax or ambiguous control flow.
- Existing host symbols for evidence extraction, baseline behavior, legal candidate registry, host approval/state checks, execution, and postcondition verification. Bindings describe existing symbols and structured data, not unrestricted snippets evaluated by the tool.
- Ordered questions, primary/evidence roles, and an exhaustive mapping from assessment labels to permitted host consequences. Represent abstention and error/fallback behavior explicitly. Do not infer a `Score` cutoff or ranking policy from its numeric value alone.
- Runtime construction and ownership, task identity and completion, feature-flag location/default, budget coordinator and canary scope, audit sink, resource bounds, and immutable-cache conditions where relevant.
- Integration-owned output paths, permitted target edits, dependency requirements, baseline/modified test command argument vectors, timeouts, and expected behavioral assertions. Unavailable prerequisites remain explicit.
- Evidence classification and the scope of authorization already supplied by the user or trusted host. Binding fields and status files cannot authorize themselves.

Do not require a user to author the final patched function. If an indispensable host binding is absent, return a precise missing-binding result and complete all independent analysis first.

### Recipe registry and source transformations

Create a code-owned registry that exposes each recipe's supported source shapes, preconditions, bindings, transformation, verification contract, and unsupported cases. The registry must contain executable behavior, not descriptions pointing back to manual wiring.

For the first complete implementation delivery, provide a working Python recipe for each A–M category below. Each may support a deliberately bounded set of source shapes; every claimed shape needs a real host transformation and behavioral test. Shared helpers are appropriate, but a generic router wrapper without pattern-specific host behavior does not fulfill all thirteen recipes.

| Pattern | Required host behavior and distinguishing check |
|---|---|
| A: before tool execution | Evaluate a bounded pre-execution decision, then recheck the host's existing action registry, arguments, approval, and state. A blocked action must cause zero executor calls. |
| B: expensive or irreversible action | Interpret scope/risk labels through an explicit host policy. The model cannot supply missing approval, increase a budget, or authorize an irreversible operation. |
| C: tool routing | Select among existing registered tools with explicit fallback. Invoke the final permitted tool at most once and preserve argument validation. |
| D: retrieval to generation | Apply declared evidence-selection semantics before generation; preserve provenance and the stated treatment of contradictory or uncertain evidence. Relevance cannot be treated as truth. |
| E: post-action verification | Check an actual host outcome against independent postconditions. A successful exit code or the verifier's positive label alone cannot establish success. Never imply that a completed side effect has been undone. |
| F: agent-loop transition | Choose only registered continue/stop/inspect transitions while retaining step limits and task identity. Prove no extra iteration or duplicate execution on fallback. |
| G: planner/executor boundary | Validate or select an existing bounded plan/step option. Generative plan creation remains with the host's generative component; deterministic legality checks remain at execution. |
| H: context retention | Select retention/pruning decisions with pinned constraints preserved. `/prune` and generative `/compact` require distinct explicit user choices; this recipe cannot silently compact text. |
| I: retry/recovery | Route to a registered recovery action with bounded retries, retained charges, and explicit treatment of non-idempotent operations. Avoid repeating a completed side effect. |
| J: delegation | Select an existing allowed specialist; preserve ownership, concurrency limits, task identity, and child result verification. No new capabilities or agents appear from free-form labels. |
| K: code review | Turn bounded review assessments into the host's defined review disposition while preserving deterministic checks. A positive model assessment cannot approve, merge, or publish a change. |
| L: graph identity/mutation | Map `same`, `related`, `different`, and uncertainty to explicit host policy. Recheck approval and revision immediately before mutation; uncertainty cannot merge entities by default. |
| M: final answer validation | Check claims against supplied evidence and route to a registered accept/inspect/revise disposition. Any answer generation or revision is an explicit separate host operation. |

Use parsed, validated source structure to select edits. Do not locate sites by keyword replacement, guessed line numbers, example filenames, or fixed function names. Preserve comments and unrelated formatting where practical. Apply bounded source-span changes or a justified syntax-preserving transformer, then parse the complete edited files again.

Specify behavior for methods, nested scopes, aliases, decorators, async functions, generators, early returns, exceptions, conditional branches, and several candidate sites in one function. If a shape is unsupported, reject it before mutation; never fall back to a broad textual replacement. Preserve host return types, exception behavior, argument evaluation order, and exactly-once side effects for supported shapes. If a signature changes, identify and update all supported callers or reject the transformation.

For JavaScript/TypeScript, retain honest analysis-only status until an executable transformer and host integration tests exist. Any implemented parser/transformer must use the trusted tooling directory and must not load target plugins or the target compiler configuration. Other languages must remain explicitly unsupported for automated rewriting until implemented and tested. The Python delivery must work without Node.

### Runtime wiring and labels

Retain `SafeRouter`, `HostGate`, strict generated factories, and the shared `BudgetCoordinator` contracts. Model output remains a proposal; host code performs the final policy check and action. Provide an explicit, validated semantic translation where assessment labels are not executable action IDs. Do not widen `allowed_actions` merely to make a classification pass validation.

The default-off path must preserve the baseline without model calls. Shadow must preserve baseline behavior, bound work, and make no treatment side effects. Existing exact-runtime-bound expiring receipts, rubric/role binding, calibration/holdout checks, task-level canary assignment, budgets, timeout/fallback behavior, cache scope, revocation, and suspension rules remain enforced.

Integrations sharing a workflow must share the same process-local coordinator and stable canary scope. Do not instantiate a coordinator per decision or reset task IDs on retry. Tests must cover multiple routers and threads; document that this is not a distributed provider limit.

Do not claim successful live activation from a fixture. Active-path unit tests may exercise the existing test-only receipt construction under explicit synthetic classification; they must not add an activation bypass to generated code or relabel test evidence as observed application benefit.

### Implementation bundle and state

Produce machine-readable artifacts with schema validation and cross-artifact integrity checks. Suggested contents are `implementation-spec.json`, `implementation-plan.json`, the existing exact patch plan, a readable diff, an implementation manifest, an owned-file/preimage record, and baseline/verification/rollback receipts.

Bind the bundle to the target root/worktree identity, baseline revision or content snapshot, exact inventory/candidate/source identities, recipe version, binding and configuration digests, and hashes of every generated or modified file. Distinguish original discovery hashes from post-edit hashes; a changed host file must not overwrite the original source evidence. Worktree creation changes the path identity: plan against the actual destination and revalidate its source rather than weakening the root check.

Use explicit transitions such as `planned`, `applied_unverified`, `verified`, `verification_failed`, `rollback_planned`, `rolled_back`, and `blocked_recovery`. Merely linking a manifest must never upgrade a state to verified. `implement-status` recomputes file identity and receipt validity rather than trusting a status string.

Define the verification trust boundary explicitly. Local hashes detect changed artifacts; they cannot authenticate execution claims when an attacker can rewrite both the bundle and its receipts. Record verified results from tool-observed execution, and require externally trusted receipt provenance when a later status check must certify those claims. Without that authority, report integrity-consistent but unverified evidence. Status checks must not silently execute target code; any fresh behavioral verification needs the authorized execution scope.

Reject tampering, drift, duplicate/overlapping edits, path escapes, protected paths, and ambiguous bindings before writing. Reconcile several selected recipes that edit the same host function into one reviewed plan or report a conflict. A second application must be idempotent, with no duplicate imports, wrappers, calls, or ownership claims.

Keep sufficient durable preimages and a bounded journal for interrupted apply/rollback. A recovery action must reconcile current hashes before continuing. Rollback restores only integration-owned changes whose current bytes match the applied plan and preserves unrelated edits. Never use a broad Git reset/clean or overwrite concurrent work. Treat process termination and a write exception as different failure cases.

Preimages, patch contents, and target test output may contain sensitive source. Keep them in the explicitly authorized local bundle; do not copy them into this repository, ordinary reports, telemetry, or release archives. Logs and published receipts should contain minimal metadata and redacted diagnostics.

### Independent verification

Capture baseline evidence before mutation through separately authorized target execution. Verify the post-edit host entry point in an isolated subprocess appropriate to the target. Reading source and generating a plan must not import target modules. Dependency installation, network access, repository hooks, Git publication, production mutation, and runtime activation are distinct scopes; infer none from the existence of a plan file.

Verification must establish all of the following for a supported recipe:

- The edited modules parse and the package imports in its intended execution environment; generated imports resolve from an installed wheel as well as this source checkout.
- The actual host entry point reaches the generated integration when appropriate. A test that only calls `adapter.propose` is insufficient.
- Default-off and shadow runs preserve the baseline's return values, exceptions, host-visible state, and side-effect counts. Show a fixture where enabled assessment changes the intended finite decision, with synthetic evidence labeled honestly.
- Unknown labels, malformed distributions, abstention, missing evidence, provider failure/timeout, low confidence, missing/revoked/expired receipts, resource exhaustion, and audit failure follow the defined fallback or block policy.
- Approval, permission, legal-action membership, and state/revision checks remain effective immediately before execution, including a state change after assessment.
- The declared postconditions hold independently of the model's assessment. An exit code or an assertion copied from the manifest is not sufficient evidence.

Use recipe-owned assertions and observed call/effect traces in the verification harness. Host-supplied postcondition functions can contribute evidence, but a function that merely returns `True` cannot prove the integration worked. Include a deceptive or ineffective host verifier in the negative tests.

Bind each test receipt to the command definition, baseline and applied file hashes, recipe/spec/runtime versions, candidate and experiment, timing, execution environment, test assertions exercised, and explicit pass/fail/timeout/not-run outcomes. Avoid arbitrary raw command or output disclosure. Missing/failed/timed-out scheduled cases remain in the denominator. A verified integration is not evidence of improved task success, calibration, or authorized deployment.

## Required tests and demonstrations

Build a complete offline demonstration that copies synthetic targets into a new temporary workspace and runs scan/review, recipe selection, plan, exact apply, host verification, status, and rollback. Keep the runtime off by default; disclose every fixture assessment. No live key, model request, or production service is required.

Add meaningful regressions for:

1. All thirteen Python recipes, with actual call-site edits and post-edit host execution. Include varied symbol names and at least one source layout not copied verbatim from `examples/` so the implementation cannot be a fixture-specific patcher.
2. Source/hash drift before planning and before apply; altered bindings, plan contents, or verification receipts; stale/wrong-root bundles; changed file modes and UTF-8/newline handling.
3. Missing/ambiguous symbols, unsupported AST shapes, invalid label mappings, rejected deterministic candidates, and absent semantic review. These must produce no target mutation.
4. Repeated plan/apply, same-function recipe conflicts, interrupted writes, partial apply failure, successful rollback, and rollback refusal after an unrelated edit. Verify ownership and preserved bytes.
5. Full host fallback and policy behavior, including late state changes and shared budgets across routers/threads. Exercise semantic labels for retrieval and graph decisions instead of testing only tool-name routing.
6. Receipt forgery and copied status claims: neither an edited `wiring_status` nor a success-shaped JSON document may establish verified wiring.
7. CLI subprocess behavior and exit statuses, thin script entry points, schema validation/copy parity, and installed-wheel module/data discovery.
8. Analysis without execution, offline demos without network, and honest unsupported TypeScript/parser behavior. Exercise trusted TypeScript support separately when present.

Run the full existing regression suite, `python scripts/validate_package.py`, the v1.1 and v1.2 synthetic demos, the new implementation demo, and authorized target suites. Update CI to exercise the new demo and real supported language paths. Existing Windows permission/symlink and encoding constraints require accurate reporting; do not delete or weaken checks to claim a pass. Report which interpreters and platforms actually ran.

## Documentation and delivery

Update code, strict schemas, tests, fixtures, CLI help, `SKILL.md`, README, integration playbook, requirements traceability, package metadata, and release notes together. Publish a support matrix naming each recipe and supported source shape, with implemented/unsupported status based on executable evidence. Remove wording that delegates an implemented transformation to manual work; retain truthful limits for all other paths.

Rebuild release checksums after the final edits and verify the exact manifest. Keep validation evidence generated by previous releases identifiable as historical. Do not manufacture observed measurements or rewrite old experiment receipts to match new code.

When the task includes repository delivery, inspect current remotes and protection rules, use a scoped branch/worktree, sign commits, push, open a concrete PR, complete required CI/review gates, merge without bypassing protection, and synchronize the local default branch. Do not claim CI matrix success before the actual jobs finish. Never shut down or terminate WSL.

In the final delivery, list the implemented recipes/source shapes, the commands that now work, the actual host-wiring evidence, validation results, unsupported cases, and whether any target remains applied but unverified. Completion requires executable integrations and independently checked results; a polished catalog or a generated adapter alone is incomplete.
