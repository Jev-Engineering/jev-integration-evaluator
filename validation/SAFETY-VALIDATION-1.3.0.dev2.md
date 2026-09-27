# JEV Integration Evaluator 1.3.0.dev2 — safety validation

The supplied-archive qualification below is historical. It describes the original dev2 artifact, before the additional guard-cleanup and definition-time binding corrections found during integration. Its engine identity, test totals and publication status apply only to that artifact. See the integration qualification addendum at the end for subsequent evidence.

## Supplied-archive qualification

Date: 2026-09-27. Classification: executed local software qualification using **synthetic hosts and fixture assessments**, not application-benefit evidence or production activation.

## Exact source and scope

Repository: `Jev-Engineering/jev-integration-evaluator`.
Baseline commit: `df1326eaa3688a3a8b8dc21d6c1fbbce9fc65231`.
Baseline Git tree: `2cadf8a327b992217e4297c86c317fcb334a6cbe`.
The live main already contains the bounded A–M implementation merged in PR #2. This follow-up repairs defects in that engine; it does not claim to implement the later repository-orchestration epic #3 or its child issues.

The source archive was reconciled to the live blob hashes and the exact complete baseline Git tree before testing. The imported baseline commit is the existing GitHub-signed merge object, not a new commit or a newly created signature. Changes were made in an isolated container worktree, branch `fix/executable-integration-safety`. The user's Windows checkout was not accessed, synchronized, reset or modified; WSL was not terminated.

## Implemented corrections

1. **Exactly-once host effects and exception identity.** Registered executors raising `UseFallback` or `PolicyBlock` after an effect previously could replay the baseline or be misclassified as a pre-execution block. The operation boundary now preserves the original exception object/type, allows the existing guard to observe it unchanged, and prevents fallback replay after an operation starts. Runtime-off/shadow original calls are outside the router-signal catch scope. Finishers, completed recovery results and guard cleanup retain completed effects. Deterministic per-step blocks still retain `PartialPlanError` results.
2. **Collected runtime ownership cannot reset budgets.** Dead router/coordinator weak references remain bounded ownership tombstones. Dropping an owner and constructing a new one under the same workflow/placement identity cannot reset the shared allowance. Both router and coordinator cases were reproduced through edited host entry points. This retains the existing 1,024-placement bound; it is not a distributed provider cap.
3. **Real source-scope binding checks.** Seam parameters, registry parameters, post-action executor parameters, module exception targets and structural-pattern captures cannot masquerade as required module symbols. Ambiguous/shadowed source is rejected before target mutation or bundle creation. No arbitrary textual rewriting was added.
4. **Verification remains bound to reviewed phase bytes and modes.** Every scratch copy must match the plan, rather than merely match a possibly drifted current source. Failed copies remain failed scheduled cases. After probes and separately authorized commands, discovery and owned files are rechecked, including baseline absence of generated output. New receipts and CLI results include `file_identity_valid`; false cannot coexist with passed status.

Schema 1.0 remains readable for historical receipts without the new field. Newly produced receipts include it. Runtime/engine hashes and external receipt provenance remain required; historical receipts are not rewritten to claim current validity. Existing specs and their older dependency floor remain readable, but that floor does not certify these corrections. Install the dev2 wheel and re-plan/review after the engine changes.

## Executed tests

| Check | Actual result |
|---|---|
| Unchanged exact-main regression suite | **557 passed**, 123.70 s pytest duration |
| New host-operation/ownership regressions | **44 cases** |
| New source-scope regressions | **17 cases** |
| New verification-identity regressions | **7 cases** |
| Complete corrected dev2 regression suite | **625 passed; 0 failed; 0 skipped**, 146.11 s pytest duration |
| Release-manifest fixture recheck | **4 passed**, retaining missing/extra/duplicate/traversal protections |
| Package/schema validation before final report | **27 mirrored schemas**, **321 synthetic records**, **13 implementation examples**, **1 replay**, **621 manifest entries** |
| v1.1 synthetic demo | Exit **0**, 80 paired tasks, 40 calibration and 120 holdout observations; synthetic adoption remains blocked |
| v1.2 synthetic demo | Exit **0**, two-gate workflow, 80 task pairs, 80 calibration and 240 holdout observations; synthetic adoption remains blocked |
| Complete implementation demo | **13 recipes**, **21 baseline cases**, **63/63 modified cases**; every target restored |
| Installed dev2 wheel | Built/installed offline; actual C host plan, baseline, apply, off/shadow/active verification, status and rollback passed |
| Trusted TypeScript parser | Node **22.16.0**, TypeScript **5.8.3**, real `typescript_ast` parse, zero errors; rewriting remains unsupported |

The initial dev2 full run had **624 passes and one failure**: the legacy package fixture omitted the newly required current validation file. The fixture now copies that required metadata while still excluding large historical validation. The complete suite was rerun successfully; the failed attempt was not omitted from the work record or relabeled as a pass. No existing test assertions were removed to bypass that failure.

The adversarial tests were run before their fixes and reproduced the failures. In the first host-boundary batch, 39 of 42 cases failed before correction; all 17 scope cases and the first six identity cases also failed before correction. The owner-reset case independently failed before the tombstone fix. These are synthetic regressions, not measurements of real user incidents.

## Actual edited-host lifecycle evidence

All recipes use the same deliberately bounded source shape, **`module-tail-call-v1`**: a flat root Python module and an undecorated synchronous top-level one-parameter function whose body is an optional docstring plus one direct baseline tail-call return. Existing module functions provide host bindings; registries are explicit and finite. The transformer preserves the public signature and uses parsed source spans. It does not ask the caller to write replacement functions.

| Recipe | Pattern | Baseline cases | Modified passes/cases | Final target |
|---|---|---:|---:|---|
| `python.A` | Before tool execution | 2 | 6/6 | rolled_back |
| `python.B` | Expensive/irreversible action | 2 | 6/6 | rolled_back |
| `python.C` | Registered tool routing | 1 | 3/3 | rolled_back |
| `python.D` | Retrieval to generation | 1 | 3/3 | rolled_back |
| `python.E` | Post-action verification | 2 | 6/6 | rolled_back |
| `python.F` | Agent-loop transition | 2 | 6/6 | rolled_back |
| `python.G` | Planner/executor boundary | 1 | 3/3 | rolled_back |
| `python.H` | Context retention | 1 | 3/3 | rolled_back |
| `python.I` | Retry/recovery | 2 | 6/6 | rolled_back |
| `python.J` | Specialist delegation | 1 | 3/3 | rolled_back |
| `python.K` | Code review | 2 | 6/6 | rolled_back |
| `python.L` | Graph identity/mutation | 2 | 6/6 | rolled_back |
| `python.M` | Final answer validation | 2 | 6/6 | rolled_back |

Modified cases cover default-off, shadow and synthetic active execution through the actual edited host entry point, not just calls to the adapter. Code-owned assertions observed the handler, intended changed finite behavior, complete offline traces and each pattern's distinguishing contract. The implementation demo exercised plan/baseline/apply/verification/unanchored status/anchored status/rollback with Node unavailable to its process. Its PATH was an empty directory, NODE_PATH/NODE_OPTIONS were removed, and node discovery was checked absent. Zero live model/network requests were required.

All 13 targets ended `rolled_back` with original bytes restored. **No demonstration target remains applied but unverified.** Unanchored intermediate status correctly remained `applied_unverified`; supplying the separately retained verification receipt digest allowed the recorded synthetic result to be checked as verified. This demonstrates that contract, not authentication of an adversary-controlled local receipt.

The installed-wheel C lifecycle was run under isolated Python with the installed package path, outside the source checkout:

| Mode | Adapter calls | Treatment handler calls | Fixture model calls |
|---|---:|---:|---:|
| Off | 1 | 0 | 0 |
| Shadow | 1 | 0 | 1 |
| Synthetic active | 1 | 1 | 1 |

The installed-wheel target was also rolled back. Package/schema imports resolved from the wheel. All model calls in this table are local fixture assessments, not provider/network requests.

Engine identity used by the demonstration and installed wheel:
`9d94d527993e46576f4b5e73221cbae6d0db261c86649e58f02dafc642beb1ec`.

## Working commands

```text
implementation-recipes --json
implement-plan --repo TARGET --inventory REVIEWED --candidate ID --spec SPEC --out BUNDLE
implement-verify --phase baseline --repo TARGET --bundle BUNDLE --approve-execution
implement-apply --repo TARGET --bundle BUNDLE --approve REVIEWED_BUNDLE_DIGEST --baseline-sha256 TRUSTED_BASELINE_DIGEST
implement-verify --phase modified --repo TARGET --bundle BUNDLE --approve-execution --baseline-sha256 TRUSTED_BASELINE_DIGEST
implement-status --repo TARGET --bundle BUNDLE
implement-status --repo TARGET --bundle BUNDLE --trusted-receipt-sha256 TRUSTED_VERIFICATION_DIGEST
implement-rollback --repo TARGET --bundle BUNDLE --approve REVIEWED_ROLLBACK_DIGEST
```

Prefix these commands with `python -m jev_integration_evaluator` or use the installed `jev-integration-evaluator` console command. Matching single-purpose scripts and the existing legacy commands remain. Actual identifiers/digests must come from the current reviewed source and trusted authorization; placeholders are not grants of authority. Baseline execution, mutation, verification, dependency installation, Git publication and activation are separate scopes.

## Limits and remaining delivery gates

Only Linux / Python **3.13.5** ran locally. Python 3.10/3.12, Windows and macOS were not run here. CI definitions were updated to include the new regression files, but **no new hosted CI jobs were started or completed for this follow-up**. The full local suite used the trusted TypeScript installation; the separate all-recipe demo was Python-only.

Methods, nested/decorated/async/generator seams, branching/multiple-statement or multi-site seams, signature-changing rewrites, dynamic/imported/aliased bindings, package-relative module layouts, ambiguous control flow, unsupported encodings and JS/TS rewriting remain explicitly unsupported. The existing host must provide real locks/gates, runtime ownership and read-only observation callbacks. The probe is not an OS sandbox or a proof against deliberately hostile native/reflection code. There is no new live provider bootstrap, activation bypass, distributed budget service, task-success improvement or production deployment claim.

No new commit was signed or created; no branch was pushed; no new PR, independent PR review or merge was performed. Local Git transport failed DNS resolution and no trusted signing identity is configured in this container. The GitHub read connector worked; its exposed low-level commit action has no signature input. An unsigned substitute was not published to satisfy a signed-commit requirement. Branch metadata reported unprotected main and the readable ruleset list was empty; the separate administrative protection endpoint returned 403, so this report does not invent a protection-gate failure. The new repository publication/review/CI/merge and user's local default-branch synchronization remain outstanding.

The delivery includes the complete changed source, a patch against the exact baseline, an offline-built wheel and minimal validation metadata. Full private target bundles, preimages, credentials, target test output and build caches are not included. Older validation directories remain unchanged historical evidence. Artifact hashes are integrity checks, not signatures or independently trusted execution attestations.

## Reproduction

```bash
python -m pytest -q
python scripts/rebuild_checksums.py --write
python scripts/validate_package.py --check-manifest
python scripts/run_v11_demo.py --out ../new-private-v11-demo
python scripts/run_v12_demo.py --out ../new-private-v12-demo
python scripts/run_implementation_demo.py --out ../new-private-implementation-demo
```

Use fresh local output directories and an already authorized environment with the declared dependencies. Do not use these commands as permission to run an arbitrary target, install software, publish Git changes, or activate a runtime. Keep newly generated private evidence local. Final artifact/manifest checks are recorded in the delivery's machine-readable validation summary.

## Integration qualification addendum — 2026-09-27

The supplied standalone source ZIP and the source ZIP inside the delivery bundle were byte-identical (SHA-256 `52a40df0393de646a0711673f3aca6caeb16d90887919e2bf617e909b6273eff`). All 621 source-manifest entries, all six delivery artifact hashes, and the wheel's 66 source/data files and RECORD hashes matched. Archive paths were checked before isolated extraction. These are integrity checks, not execution attestations.

Independent source review identified three additional gaps in that artifact:

- Recipe E swallowed a postcondition guard's cleanup exception and could finish with success after its effect. Recipe G could replace a guard cleanup `PolicyBlock` with `PartialPlanError`. Four new regressions reproduced three failures before correction. Guard exceptions now remain distinct from body policy failures, preserving exception identity and stopping finishing after failed cleanup; genuine later-step preflight blocks still retain completed results.
- Module-scope callback rebinding inside unrelated function defaults/decorators or class decorators/bases/keywords escaped the binding collector. Eight adversarial cases were wrongly accepted before correction. Definition-time expressions are now checked, while ordinary function/class-local bodies and lambda bodies retain their separate scopes. A ninth control test checks those scopes. Fixtures include an import-failing sentinel; planning neither imports nor mutates them.
- The README referred to an absent dev2 validation directory; it now links to this report and distinguishes earlier release evidence.

Fresh local qualification ran on a byte-matched native Linux snapshot under WSL, Python **3.12.3**, with existing dependencies and Node unavailable:

| Check | Observed result for the integrated code |
|---|---|
| Host boundary and runtime regressions | **91 passed** |
| Source-scope and recipe regressions | **39 passed** |
| Complete regression suite | **637 passed, 1 skipped**, 45.30 s; only the optional trusted TypeScript parser test skipped |
| Installed-wheel host lifecycle | Passed as part of the full suite; isolated imports, baseline, apply, off/shadow/active verification, anchored status and rollback |
| Package validation | **27 mirrored schemas**, **321 synthetic records**, **13 implementation examples**, **1 offline replay** |
| v1.1 and v1.2 offline demonstrations | Both exited **0**; synthetic adoption remained blocked |
| A–M implementation demonstration | **13 recipes**, **21 baseline cases**, **63/63 modified cases**; every synthetic target restored, zero applied/unverified targets |

Engine identity for the corrected demonstration and wheel:
`b02ccae4787da8e970a08421abc3677a8e75578f1c0b4e94cb4b87b3cb008b57`.

This identity differs from the supplied archive. The supplied prebuilt wheel does not contain the integration corrections; use a wheel rebuilt from the merged source. Re-plan and review bundles after changing engine versions. The original archive's qualification above must not be used for this changed tree.

Hosted CI, signed publication and merge are tracked by the associated pull request, separately from these local observations. The local parser skip is explicit; it is not a claim that the TypeScript-enabled CI matrix ran locally. Windows and macOS runtime suites were not run for this integration. All behavior evidence remains synthetic, with no live provider connection, production activation or measured application benefit. Epic #3 and issues #4–#15 remain outside this safety repair.
