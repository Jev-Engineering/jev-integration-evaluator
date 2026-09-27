# Executable JEV integrations — 1.3.0.dev3 qualification

The supplied-archive qualification below is historical. It was built from the original dev2 delivery and predates PR #16 and the additional dev3 integration corrections. Its test totals, engine identity and publication limitations describe that artifact, not the integrated tree. The `validation/executable-v1.3.0.dev3/` files retain that same archive evidence unchanged. See the integration qualification addendum at the end for subsequent validation.

## Delivery disposition

Source implementation and local qualification completed on 2026-09-27. **Repository publication is blocked:** the connected GitHub `create_blob` action returned HTTP 403, `Resource not accessible by integration`, before creating any blob, branch or commit. No further write workaround was attempted. Direct Git transport also failed DNS resolution; no local signing key is configured. No new signed commit, remote branch, PR, independent review, hosted CI, merge or Windows checkout synchronization is claimed.

This is a continuation of the supplied executable-integration specification, not a replacement roadmap or an arbitrary-repository implementation command. The source preserves the A–M bounded engine and dev2 fixes, and adds verified failure-accounting and source-fidelity corrections. No real provider, live key, production service or activation was used.

## Source provenance and preservation

- Actual GitHub base: `df1326eaa3688a3a8b8dc21d6c1fbbce9fc65231`; exact Git tree `2cadf8a327b992217e4297c86c317fcb334a6cbe`. The supplied prompt's `1cca65a` baseline is historical.
- The original dev2 archive SHA-256 is `52a40df0393de646a0711673f3aca6caeb16d90887919e2bf617e909b6273eff`. Its 621 manifest hashes were checked. Reversing its patch reproduced the entire actual-main Git tree exactly.
- Only the exact existing GitHub merge-commit object was imported after matching its object SHA. GitHub reports its historical signature valid; this is not a new signature and was not represented as locally cryptographically verified.
- Local branch/worktree: `fix/executable-verification-dev3` on that existing commit. The new work remains uncommitted. The separate exact baseline is clean; the user's Windows checkout and WSL were not changed.
- All **28 pre-existing dev2 test/support files** and **358 historical validation files** are byte-for-byte unchanged. Two new test files add **38 cases**. Existing dev2 release artifacts are untouched.
- Current implementation engine content identity: `c93ded9292a77316861b4f940abb57d3aaaffc2293f4ba69910828e927e20484`. This is a content identity, not a commit, signature or approval.

## Corrections implemented in this continuation

| Boundary | Reproduced defect | Implemented correction |
|---|---|---|
| Probe validity | A JSON `null` probe with successful process exit could pass baseline verification; malformed output could crash receipt production. | Strict mirrored observation schema plus recipe-bound roles/arity; invalid output becomes a failed scheduled row with the invalid payload excluded. |
| Required command execution | A missing executable raised instead of preserving a complete phase receipt. | Record command `not_run` and null return code; retain all probe rows and block the phase. Embedded NUL argv is rejected during planning. |
| Receipt completeness | Rehashed rows could omit or duplicate cases or change mode/count/command identity. | Validate the exact ordered schedule, completed count, observation presence/structure and required command digest against the reviewed spec. |
| Interrupted re-verification | An older passing receipt could remain certifiable after a newer interrupted run. | Fsync `verification_started` before modified execution; a nonterminal run yields `blocked_recovery`. Fresh authorized verification or exact owned-byte rollback can recover. |
| Source fidelity | Import insertion could split a leading unrelated decorator from its definition; declared non-UTF-8 cookies could be accepted based on byte decoding alone. | Insert before the earliest decorator and validate Python's declared codec. Equivalent UTF-8 aliases remain accepted; unsupported encoding fails before bundle creation. |

The dev2 effect boundaries, retained budget-owner tombstones, scope checks and final file/mode checks are retained. No runtime dependency or activation bypass was added. Public names remain `jev-integration-evaluator` and `jev_integration_evaluator`. The new observation contract is available through the CLI and installed wheel; valid older receipt shapes remain identifiable by their original engine identity, not silently recertified.

## Executable support matrix

All entries below are implemented and locally exercised through actual edited host entry points. Every recipe still uses the qualified `module-tail-call-v1` shape: a flat UTF-8 Python module, undecorated synchronous top-level function, one required positional input, optional docstring/comments, and one direct named baseline tail-call return. Registries and required host callbacks already exist and must be source-bound. The engine generates host edits; the caller does not supply a complete replacement function.

| Recipe | Placement | Distinguishing behavior |
|---|---|---|
| A | Before tool execution | Blocked actions produce zero executor calls. |
| B | Expensive or irreversible action | Risk/scope labels cannot override host approval or budgets. |
| C | Registered tool routing | Only a permitted existing tool is invoked, at most once. |
| D | Retrieval to generation | Selection retains provenance and declared contradictory/uncertain evidence. |
| E | Post-action verification | Observed outcome and independent postcondition checks; no claim of undoing effects. |
| F | Agent-loop transition | Only registered continue/stop/inspect outcomes within host limits. |
| G | Planner/executor boundary | Bounded existing steps, per-step gates and preserved partial outcomes. |
| H | Context retention | Pinned constraints retained; /prune remains separate from /compact. |
| I | Retry/recovery | Retained charges and bounded recovery without replaying completed effects. |
| J | Specialist delegation | Registered specialists, shared ownership/limits and child verification. |
| K | Code review disposition | Deterministic checks retained; no automatic approve/merge/publish authority. |
| L | Graph identity/mutation | Explicit same/related/different/uncertain mapping with revision/approval gates. |
| M | Final answer validation | Finite accept/inspect/revise outcome, not automatic answer generation. |

Unsupported: selected methods, nested scopes, decorators, async/generators; branching/multiple candidate sites/signature-changing rewrites; package-relative/cross-module/imported/dynamic bindings; non-UTF-8 or BOM source; JavaScript/TypeScript or other-language rewriting. Unrelated decorated definitions are preserved, but this does not add decorated selected-seam support. The native TypeScript path remains analysis-only. Missing host prerequisites receive explicit failure instead of invented policy/provider ownership.

## Actual validation

| Check | Executed result |
|---|---|
| Unchanged dev2 full regression baseline | 625 passed; 0 failed; 0 skipped; 167.02 seconds |
| Corrected initial regression reproducer against old code | 22 failures reproduced before production fixes |
| New focused regression corpus after fixes | 38 passed; 41.89 seconds |
| Final dev3 full regression suite | **663 passed; 0 failed; 0 errors; 0 skipped**; 256.455 seconds |
| Package contracts/examples | 28 identical mirrored schemas, 321 existing synthetic records, 13 binding/transform examples and one new observation example |
| Existing v1.1 and v1.2 offline workflows | Passed; synthetic evidence remains ineligible for activation/adoption |
| Full CLI lifecycle with Node absent from PATH | 13 recipes, 21 baseline cases, **63/63 modified cases**; externally anchored versus unanchored status checked; all targets rolled back |
| Separate installed-wheel lifecycle, outside checkout and without Node | 13 recipes, 21 baseline cases, **63/63 modified cases**; all targets rolled back |
| Installed artifacts | 68 module/data files match final source, 28 schemas, 73 RECORD entries verified; new observation CLI validation passed |
| Native TypeScript analysis | Node v22.16.0, TypeScript 5.8.3; actual `typescript_ast`, one function, zero diagnostics; trusted tooling only |
| Process termination/recovery | Real child `os._exit(23)` and KeyboardInterrupt cases; old pass excluded; fresh verification and owned rollback exercised |
| Source fidelity | Actual host execution after unrelated decorated function/class preservation; exact rollback; invalid codec rejection and UTF-8 alias acceptance |

The first eight-test development reproducer included two fixture-preparation errors caused by Python interpreting intentionally invalid encoding cookies in the helper; the helper was corrected before the definitive 22-case old-code reproduction. One expanded intermediate test invocation hit the tool's outer runtime limit and produced no complete result; it is not counted as a pass or an assertion failure. Completed 38-case and final 663-case runs supersede that incomplete attempt. No assertion was weakened or old test removed.

Only **Linux / Python 3.13.5** ran here. The edited CI configuration still declares other Python versions, but those jobs and Windows/macOS were not run in this environment. All numerical task/host results are deliberately synthetic. No live provider latency, cost, accuracy, measured downstream benefit or production activation is established.

### Installed-host evidence: recipe C

| Mode | Adapter calls | Treatment-handler calls | Fixture-model calls |
|---|---:|---:|---:|
| Off | 1 | 0 | 0 |
| Shadow | 1 | 0 | 1 |
| Synthetic active | 1 | 1 | 1 |

These calls came through the edited host entry point, not a direct adapter-only test. Baseline return/state/effect parity, recipe-specific contracts and exact-byte rollback were checked. The CLI demonstration and installed-wheel run are separate executions using synthetic fixtures; they are not independent empirical studies of application effectiveness.

## Working command surface

Uppercase values below are explicit input placeholders, not guessed candidate IDs or fabricated approval digests. The matching `scripts/implementation_recipes.py`, `implement_plan.py`, `implement_verify.py`, `implement_apply.py`, `implement_status.py` and `implement_rollback.py` remain available.

```bash
jev-integration-evaluator implementation-recipes --json
jev-integration-evaluator implement-plan --repo TARGET --inventory REVIEWED --candidate ID --spec SPEC --out BUNDLE
jev-integration-evaluator implement-verify --phase baseline --repo TARGET --bundle BUNDLE --approve-execution
jev-integration-evaluator implement-apply --repo TARGET --bundle BUNDLE --approve REVIEWED_BUNDLE_DIGEST --baseline-sha256 RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo TARGET --bundle BUNDLE --approve-execution --baseline-sha256 RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo TARGET --bundle BUNDLE --trusted-receipt-sha256 EXTERNALLY_AUTHENTICATED_RECEIPT_SHA256
jev-integration-evaluator implement-rollback --repo TARGET --bundle BUNDLE --approve REVIEWED_ROLLBACK_DIGEST
jev-integration-evaluator validate --kind implementation-observation --input OBSERVATION_JSON
```

Omit `--trusted-receipt-sha256` for an integrity-only status check; without authenticated receipt provenance, an intact applied target is `applied_unverified`, not certified execution. A digest generated by a model is not permission to apply an unseen patch. Planning/status do not execute target modules. Runtime off is the default; synthetic active verification does not authorize real exposure.

## Trust, recovery and remaining gates

A schema, local content hash or self-consistent journal does not authenticate an adversarial host or writer. Verification validates its observation envelope and recipe-owned assertions, but subprocess/environment filtering is **not a security sandbox**. Additional target-native suites need their own explicit authorization and appropriate external isolation. This release does not add a general sandbox or certify hostile code.

Private source, preimages, raw target output and activation fixtures stay in local temporary bundles; they are not included in this release. Published evidence is test metadata and fabricated demonstration data. All CLI-demo and installed-wheel targets were restored, and their temporary bundles were removed. **No target remains applied but unverified.**

The source and test delivery is ready for review, but signed repository publication, independent review, hosted CI, merge and local default-branch synchronization remain outstanding because repository writes were denied. No issue or epic was closed. Existing future repository-command/provider-bootstrap/expanded-language work is not claimed complete by this bounded-engine package.

## Integration qualification addendum — 2026-09-27

The delivery ZIP SHA-256 was `8359ef4289b4d6fa9832941950d8d407d52168e1123e87b2df1f247ccec54bf5`. Independent archive inspection verified all ten artifact hashes, all 639 supplied source-manifest hashes, and all 68 wheel source/data files plus RECORD hashes. Extraction rejected unsafe paths and checked collisions and containment. These hashes establish artifact integrity, not execution authenticity.

The archive was based on the original dev2 delivery, while current main was already `1753f05994ccd54178a315c216ed0ffc33b5e2b8` from PR #16. Integration used that original dev2 tree as the common ancestor and reconciled the dev3 delta with current main. All 387 existing test, validation-history and host-runtime files were byte-preserved, including the guard-cleanup and definition-time binding fixes and their regressions. The README conflict was resolved to link to this report; existing validation history was not replaced by older archive copies.

Review added four corrections to the supplied dev3 code: locate the actual opening decorator token for multiline forms; durably mark interrupted baseline verification so an older pass cannot authorize apply; reject command status/exit-code contradictions; and keep aggregate receipts within the JSON reader's byte limit while retaining overflow rows as failed scheduled cases. Baseline completion preserves rolled-back and incomplete-mutation dispositions. All corrections remain within the existing bounded Python engine.

The supplied prebuilt wheel predates this reconciliation and these fixes. Consumers must use a wheel rebuilt from the integrated source, and create/review fresh bundles when the engine identity changes. The supplied-archive evidence above and under `validation/executable-v1.3.0.dev3/` cannot qualify the changed engine. Hosted CI, signed publication and merge evidence belong to the associated pull request, separately from local synthetic qualification. Roadmap epic #3 and issues #4 through #15 remain outside this repair.

Fresh qualification ran on a byte-matched native Linux snapshot under WSL, Python **3.12.3**, using existing dependencies with Node unavailable:

| Check | Observed result for the integrated code |
|---|---|
| Complete regression suite | **693 passed, 1 skipped**, 62.70 seconds; only the optional trusted Node/TypeScript parser test skipped |
| Failure/lifecycle/identity/command regressions | **90 passed** |
| Source-fidelity/scope/recipe regressions | **49 passed** |
| Command receipt combinations | **10 passed**, retaining legitimate failed commands with exit code zero |
| Installed-wheel lifecycle | Passed within the full suite: isolated imports and recipe C baseline/apply/off-shadow-active/status/rollback |
| Package validation | **28 mirrored schemas**, **321 synthetic records**, **13 implementation examples**, **1 observation example**, **1 replay** |
| v1.1 and v1.2 offline demonstrations | Both exited **0**; synthetic adoption remained blocked |
| A–M implementation demonstration | **13 recipes**, **21 baseline cases**, **63/63 modified cases**; every target restored, zero applied/unverified targets |

Ten integration regression failures were reproduced before their corrections: two multiline-decorator failures, two baseline-interruption failures, four contradictory command receipts, and two aggregate receipt-size failures. The size tests use a reduced reader budget and formatting-heavy observations, exercising exact serialized-byte accounting without a large stress allocation. All corresponding regressions pass; no existing assertions were removed or weakened.

Corrected engine identity used by the demonstration and installed-wheel suite:
`15638e2b79b2a301a09326bc35f447bb1af5ba950766183147c2c3154ffd1877`.

Windows and macOS runtime suites were not executed for this integration. Hosted Python 3.10/3.12/3.13 and TypeScript qualification is reported by CI, not inferred from the local parser skip. All runtime results remain synthetic; no real provider connection, production activation or measured application benefit is established.
