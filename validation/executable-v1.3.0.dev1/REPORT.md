# Executable JEV integrations — local development delivery

Version: **1.3.0.dev1**  
Implementation base: `075f8f39eb06283ded15f71c08aa243cea04acd4`  
Evidence date: **September 27, 2026**  
Status: **implemented and locally tested; not committed, published, or merged upstream**.

## Delivered behavior

This delivery implements all thirteen Python A–M recipes for the deliberately bounded `module-tail-call-v1` source shape. The planner derives actual host call-site edits and a default-off integration module from AST anchors, reviewed source identities, and explicit existing-symbol bindings. It does not ask the caller to write the final replacement function. Planning does not import or execute the target.

The supported seam is a synchronous, undecorated module-level function in a flat root Python module, with one required argument and a single tail return of an existing named baseline function on that unchanged argument. Optional docstrings, comments, UTF-8 content and LF/CRLF are supported. Static finite registries and fixed-arity existing host callbacks are prerequisites. No public signature change or caller rewrite is needed for this shape. Missing or ambiguous bindings and unsupported shapes are rejected before mutation.

| Recipe | Implemented host behavior and distinguishing evidence |
|---|---|
| A — before tool execution | Bounded assessment followed by current registry, arguments, approval and state checks; blocked action has zero executor calls. |
| B — costly/irreversible action | Explicit scope, finite cost, affordable budget and irreversible approval; no model authority to increase them. |
| C — tool routing | Explicit label-to-registered-tool mapping and fallback; final permitted tool invoked at most once. |
| D — retrieval to generation | Existing evidence subset selection with original provenance and contradictory/uncertain records retained; relevance is not truth. |
| E — post-action verification | Actual outcome and before/after host state are checked independently; an always-true host verifier cannot make an ineffective action pass. Completed effects are not replayed or described as undone. |
| F — loop transition | Finite continue/stop/inspect choices, stable task identity and real host-loop limits; observed iterations/effects remain bounded. |
| G — planner/executor boundary | Existing bounded plans with unique registered steps; current execution checks per step; completed results survive partial policy failure. |
| H — context retention | Pinned constraints retained; pruning requires explicit choice; compaction remains a distinct host operation. |
| I — retry/recovery | Existing recovery registry, atomic bounded retry reservation and retained charges; completed or unsafe non-idempotent effects are not repeated. |
| J — delegation | Existing specialists, task ownership and shared process-local concurrency; child results independently checked. |
| K — code review | Finite review disposition with deterministic checks preserved; no approval, merge or publication capability. |
| L — graph identity/mutation | Explicit same/related/different/uncertain policy; current revision and approval checked before mutation; uncertainty does not merge. |
| M — final answer validation | Supplied claims/evidence and independent checks drive accept/inspect/revise; generation or revision remains a separate host operation. |

The generated adapters retain `SafeRouter`, strict exact-runtime activation receipts, `HostGate`, shared `BudgetCoordinator`, task/canary scope and the existing fallback and suspension contracts. The optional exhaustive semantic-label mapping is part of receipt/cache identity; legacy behavior is unchanged when it is absent. Semantic labels do not become execution grants.

## Implemented command lifecycle

The following commands run through both the package CLI and matching thin scripts:

```text
implementation-recipes --json
implement-plan --repo TARGET --inventory REVIEWED --candidate ID --spec SPEC --out BUNDLE
implement-verify --phase baseline --repo TARGET --bundle BUNDLE --approve-execution
implement-apply --repo TARGET --bundle BUNDLE --approve REVIEWED_BUNDLE_DIGEST --baseline-sha256 TRUSTED_BASELINE_SHA
implement-verify --phase modified --repo TARGET --bundle BUNDLE --approve-execution --baseline-sha256 TRUSTED_BASELINE_SHA
implement-status --repo TARGET --bundle BUNDLE
implement-status --repo TARGET --bundle BUNDLE --trusted-receipt-sha256 EXTERNALLY_TRUSTED_SHA
implement-rollback --repo TARGET --bundle BUNDLE --approve REVIEWED_ROLLBACK_DIGEST
```

Prefix these with `jev-integration-evaluator` or `python -m jev_integration_evaluator`. A digest is content identity, not authority to apply an unseen patch. Execution, modification, installation, network access, publication and activation remain separate scopes. The complete argument contracts and binding examples are in `references/executable-integrations.md` and `examples/implementation/`.

Bundles remain outside the target. They contain the strict specification, original reviewed inventory, source identities, generated patch and readable diff, manifest, verification schedule, owned preimages and journal. Apply reuses the existing protected-path/exact-digest patch engine. Durable recovery reconciles observed bytes after process interruption. Rollback restores only matching integration-owned bytes and refuses concurrent edits to them; unrelated files are preserved. No broad Git reset or clean is used.

## Actual local validation

| Check | Observed result |
|---|---|
| Full regression suite | **556 passed**, zero failed or skipped, Python **3.13.5**, Linux; 125.94 seconds in the final-package rerun. |
| Explicit trusted TypeScript parser suite | **31 passed** using Node **22.16.0** and TypeScript **5.8.3**. This qualifies analysis, not rewriting. |
| Strict package validation | **27 schemas**, **321 synthetic records**, **13 source-matched binding examples** validated; no target execution or network in this validator. |
| Retained v1.1 synthetic demo | Passed; 80 task pairs, 40 calibration and 120 holdout observations, five robustness probes. Synthetic adoption remained blocked. |
| Retained v1.2 synthetic demo | Passed; two gates, 240 holdout observations, 80 monitoring tasks, shared-budget/shadow fixtures. Synthetic adoption remained blocked. |
| Complete A–M CLI implementation demo | **13 recipes**, **21 baseline executions**, **63 modified executions** across off/shadow/enabled modes, and **52 code-owned contract assertions**. All checks passed. |
| Installed-wheel integration | Passed inside the regression suite: offline wheel build/install, isolated installed-package imports and schema discovery, actual transformed-host lifecycle and rollback. |
| Recovery and integrity regressions | Actual process termination during apply/rollback, separate write failures, drift/tampering, copied success claims, idempotence, mode/encoding checks, unsupported shapes, late policy changes, failure fallback, threads and shared budgets passed. |

The exact new demo engine identity is:

```text
336290228d4fdc3ca413b36cb76b0101e513e1ad4ced8874ddddc6b2021ff994
```

The qualification summary and the implementation-demo summary are provided as JSON next to this report. Passing output logs contain only the test progress and counts; private bundle preimages, target test output and provider traffic are not included in this release evidence.

**All thirteen new demonstration targets were rolled back with original bytes restored. No user production target was applied. No target from the delivered demonstration remains applied but unverified.**

## Verification trust boundary

Verification runs the actual host entry point in a fresh, byte-matched source copy, observes calls/effects and host-visible state, and checks recipe-owned assertions. Default-off and shadow are compared with a preserved baseline. Scheduled failures and timeouts remain in the denominator. A verifier returning `True`, an exit code of zero, or a manifest asserting success cannot by itself establish wiring.

All active-path demonstrations use openly synthetic provider responses and the existing test-only receipt mechanism injected into the declared runtime binding by the authorized probe. Generated production code has no test activation bypass. This verifies source transformations and host consequences, **not real provider bootstrap, application improvement, calibration, task success, live activation or deployment permission**.

A later status check without independently trusted receipt provenance reports applied/unverified even when local artifacts are integrity-consistent. Supplying an independently retained trusted exact receipt hash allows the matching observed synthetic verification to be recognized. Someone able to rewrite both a bundle and its receipts can forge local hash-consistent claims; this is not cryptographic hostile-execution attestation.

Subprocess isolation and ordinary Python network/process restrictions are not an OS security sandbox. Trusted observational callbacks, stable registries and a correct existing host lock are required. Untrusted code requires appropriate external isolation. Shared budgets/concurrency are process-local, not distributed provider limits.

## Explicit unsupported and unqualified paths

Methods, nested functions, decorators, imported/aliased bindings, asynchronous functions, generators, conditional/multiple-statement seams, dynamic registries, ambiguous sites, recursive seams, changed signatures, package-relative layouts and multi-recipe composition in the same file are not automated by this delivery. BOM, non-UTF-8 and bare-CR sources are rejected. Score-driven execution policies are not inferred; primary implementation questions are Choice with supported Noul evidence. Other shapes receive precise unsupported/blocked results before mutation.

JavaScript and TypeScript remain analysis-only; other languages have no automatic transformation claim. Python recipes do not require Node. The updated CI configuration schedules additional Python/Node paths, but **those new remote jobs have not run**. Python 3.10/3.12 and Windows were not executed in this environment, and no CI matrix success is claimed.

## Source and historical-evidence provenance

The evaluator was reconstructed from the user's retained v1.2.0 archive and reconciled against GitHub. Before changes, the package, schemas, scripts, tests, examples, references and CI directory matched the upstream Git tree hashes recorded in `source-provenance.json`. The README, integration playbook and original engineering prompt were also reconciled with their exact upstream blob hashes. This is evidence for the implementation base; it is not a claim that every reconstructed historical artifact is byte-identical to GitHub's whole root tree.

All **348 historical validation files** from the retained `jev-placement-skill-1.2.0.zip` were preserved byte-for-byte. Their pre-rename names and old measurements remain historical. They were not rewritten to make current code appear validated, and they do not reintroduce removed public command aliases. Current evidence is isolated in this versioned directory.

The portable source patch intentionally omits `SHA256SUMS`: historical file sets may differ between the retained archive and a Git checkout. Apply the reviewed patch to the matching base, then explicitly regenerate and validate that checkout's exact release manifest with:

```bash
python scripts/rebuild_checksums.py --write
python scripts/validate_package.py --check-manifest
```

The supplied source ZIP has its own complete exact-file checksum manifest. Old measurements remain historical regardless of that manifest.

## Repository delivery status

No upstream branch, signed commit, push, pull request or merge was performed. GitHub connector reads worked; direct Git cloning in this runtime failed DNS resolution and no usable signing identity was available. The user's Windows checkout and WSL were not accessed or modified. The new CI workflow is included for review, but it has no completed remote run for these edits.

This is therefore a **tested local development implementation**, not a completed signed-and-merged repository delivery or a production qualification. Source, patch, wheel and reproducible offline evidence are supplied instead of claiming those steps occurred.

## Reproduce locally

From the extracted source in an environment with the declared dependencies already installed:

```bash
python -m pytest -q
python scripts/validate_package.py --check-manifest
python scripts/run_v11_demo.py --out ../jev-v11-recheck
python scripts/run_v12_demo.py --out ../jev-v12-recheck
python scripts/run_implementation_demo.py --out ../jev-implementation-recheck
```

Use new or empty output directories. Dependency installation and any real target execution require their own appropriate authorization. The last command uses only new synthetic targets and requires no live key or provider request.
