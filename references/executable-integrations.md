# Executable Python integrations — development support contract

Version: **1.3.0.dev2**. This is a bounded implementation engine, not a general-purpose program rewriter or production activation certification. Public CLI and package names remain `jev-integration-evaluator` and `jev_integration_evaluator`. Legacy commands and receipts are retained.

## What the engine actually edits

`implement-plan` reads the reviewed inventory and a strict binding specification. It parses the selected module, matches a qualified symbol and SHA-256 of its AST statement, checks the complete source hashes and existing bindings, derives an exact call-span edit, inserts a unique import after any module docstring/future imports, and emits a default-off integration module. Both complete output modules are parsed again. It never imports target code during discovery or planning. The caller supplies existing symbol names and structured policy, **not the replacement function source**.

The supported seam is `module-tail-call-v1`: a synchronous, undecorated, top-level function in a flat Python module at the target root. It has one required input parameter, an optional docstring/comments, and one return of an existing named baseline function called with that unchanged parameter. Qualified host symbols, bindings, the baseline function, and the observed entry point must be unambiguous module-level functions with the declared arities. Host bindings and registry symbols must remain stable; the host still owns their implementation, permissions and synchronization.

```python
# Arbitrary existing names; these are not a hard-coded filename or patch template.
def decide_next(request):
    """Existing finite-decision seam."""
    return existing_host_behavior(request)
```

The generated call passes the already existing bindings to the installed pattern-specific host implementation. It neither changes the public signature nor edits unrelated callers. The verifier can invoke a different existing entry point that reaches the selected seam, including a bounded host loop. Registry callbacks must return an explicit dictionary literal, a uniquely defined module dictionary, or `dict(that_dictionary)` with the built-in `dict` unshadowed. Dictionaries map existing IDs to existing function symbols, fixed ID lists, or permitted finite disposition values, depending on the recipe. Dynamic registries are rejected before mutation. Runtime registry values and policy are checked again immediately before execution under the host's existing guard.

The post-action recipe additionally requires its baseline wrapper to return one named executor call on the same parameter. Effect observations are derived from the parsed registry/consumer and must exactly cover those symbols for effectful recipes; observing an unrelated no-op function cannot substitute for observing the executor.

## Recipe support matrix

Every row below has an actual source transformation and edited-host execution test in `tests/test_executable_recipes.py`. The common bounded source shape above applies to every row; this table does not claim arbitrary Python coverage.

| ID | Pattern-specific host behavior | Distinguishing observed check |
|---|---|---|
| `python.A` | Pre-execution decision; only the registered baseline action can proceed after current argument, membership, approval and state checks. | A blocked proposal invokes zero executors. |
| `python.B` | Existing scope/risk callback must supply finite affordable cost, scope authorization, and explicit approval for an irreversible action. | Insufficient budget or late approval loss executes nothing; the assessment cannot enlarge either. |
| `python.C` | Translate semantic labels into existing registered tools and an explicit abstain/fallback policy. | Exactly one final permitted executor; late argument, membership or approval changes block. |
| `python.D` | Select records by existing ID sets before the existing generator; preserve complete records/provenance and all contradictory or uncertain records. | Consumer receives the selected original records, not a truth assertion inferred from relevance. |
| `python.E` | Execute the baseline side effect once, observe before/after state and the actual return, then check declared state changes independently of the host/model verifier. | A deliberately always-true verifier cannot make an ineffective action pass; completed outcomes are retained. |
| `python.F` | Return only existing continue/stop/inspect transitions while retaining task identity and a step limit. | Actual host-loop iterations and effects are counted; no extra iteration/model call at the limit. |
| `python.G` | Select a bounded existing plan with unique registered step IDs; recheck each step under the host guard. | No plan generation or duplicate non-idempotent steps; partial policy failure raises `PartialPlanError` with completed results. |
| `python.H` | Apply retention choices to supplied items with pinned items preserved. | `/prune` is an explicit input choice; `/compact` does not invoke a generator or silently prune. |
| `python.I` | Select existing recovery actions, retain charges, require an atomic host retry reservation, and check completion/idempotence. | A completed effect is never replayed; unknown non-idempotent outcomes and invalid retry reservations block. |
| `python.J` | Delegate to an existing specialist with shared process-local concurrency, ownership and task identity checks. | Child results are independently checked; failed child verification returns inspection with the real completed result. |
| `python.K` | Map review labels to finite host review dispositions, with deterministic failures overriding positive model assessments. | No approval, merge or publication operation is supplied or invoked by the handler. |
| `python.L` | Explicitly map same/related/different/uncertain; compare the graph revision and require current approval immediately before mutation. | Uncertainty cannot merge; a late revision/approval change causes zero mutation calls. |
| `python.M` | Check supplied claims/evidence and independent host checks, then return accept/inspect/revise. | No answer generation/revision happens inside this recipe. |

Unsupported transformations include methods, nested scopes, aliases/imported bindings, decorators, async functions, generators, branching or multiple-statement seams, multiple candidate sites in one function, changed signatures, recursive seams, BOM/non-UTF-8/bare-CR files, dynamic registry construction, package-relative module layouts, and other languages. JavaScript/TypeScript remain **analysis only**. Python rewriting does not need Node. Multiple recipes modifying the same file are not composed: their old-source hashes conflict, with zero duplicate imports/wrappers. Re-scan and review a new plan after any intervening change.

This release does not implement an OS security sandbox or distributed budget limiter. Qualification evidence is for the interpreter/platform recorded by the local tests, not every advertised Python interpreter or Windows. Existing Windows permission/symlink constraints are not waived; platform failures must be reported, not suppressed.

## Binding specification and examples

See `schemas/implementation-spec.schema.json`, its identical packaged copy, and `examples/implementation/a` through `m`. Each example contains unmodified synthetic source, an actual source-matched reviewed inventory and a strict binding specification. `scripts/implementation_fixtures.py` can regenerate them under different symbols and paths. No example is a live application or graph-database integration.

The specification binds the candidate and experiment; full reviewed-inventory digest and scan fingerprint; original full-file and symbol-body hashes; AST statement hash; recipe ID/version/shape; existing host symbols; an explicit source-matched binding review; ordered Choice/Noul questions and primary/evidence roles; exhaustive label-to-consequence mappings with null abstention; recipe-specific policy; runtime construction ownership, configuration, coordinator, task identity, audit and bounds; exact owned paths/dependency; scheduled synthetic host inputs, expected values/exceptions/state/effect counts and optional test argv/timeouts; and a non-authoritative record of already supplied authorization.

The scanner's heuristic placement label is retained. A separate source-matched binding review identifies the actual recipe; it cannot waive rejected deterministic/hard-real-time candidates, missing semantic review or source drift. A score alone never establishes eligibility. Missing/ambiguous bindings return a blocked result; unsupported shapes return an unsupported result. Unrestricted snippets, shell strings, implicit Score cutoffs and user-authored replacement functions are not binding fields.

Only Choice/Noul implementation probes are supported. Primary questions must be Choice; semantic labels are validated and explicitly translated to host action IDs without adding those labels to the host's legal action registry. Mapping changes are included in the runtime receipt and cache contracts. Old receipts without this optional mapping retain their previous hashes and semantics.

## Executable command lifecycle

Run these commands from an installed environment, or use `python -m jev_integration_evaluator`. Every command has a matching thin script under `scripts/`. `implementation-recipes --json` lists the executable registry. The synthetic demo below is immediately runnable without a key or network:

```bash
python scripts/run_implementation_demo.py --out /new/private/demo-output
```

For a reviewed real target with supported source and explicitly authorized local synthetic checks:

```text
jev-integration-evaluator implement-plan --repo TARGET --inventory REVIEWED.json --candidate ID --spec SPEC.json --out PRIVATE_BUNDLE
jev-integration-evaluator implement-verify --phase baseline --repo TARGET --bundle PRIVATE_BUNDLE --approve-execution --out PRIVATE_BASELINE_COPY.json
jev-integration-evaluator implement-apply --repo TARGET --bundle PRIVATE_BUNDLE --approve REVIEWED_BUNDLE_DIGEST --baseline-sha256 TRUSTED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo TARGET --bundle PRIVATE_BUNDLE --approve-execution --baseline-sha256 TRUSTED_BASELINE_RECEIPT_SHA256 --out PRIVATE_VERIFICATION_COPY.json
jev-integration-evaluator implement-status --repo TARGET --bundle PRIVATE_BUNDLE
jev-integration-evaluator implement-status --repo TARGET --bundle PRIVATE_BUNDLE --trusted-receipt-sha256 EXTERNALLY_RETAINED_VERIFICATION_SHA256
jev-integration-evaluator implement-rollback --repo TARGET --bundle PRIVATE_BUNDLE --approve REVIEWED_ROLLBACK_DIGEST
```

The baseline and verification commands return a `receipt_sha256`. Retain these through a trusted channel outside the mutable bundle. `--approve` is the reviewed **bundle digest**, not the underlying legacy patch digest; the plan contains both. Inspect the readable diff and bindings before giving mutation authority. The rollback digest is available from `implement-status`, independently of verification. A digest generated by a model or read from an untrusted file is not permission to apply unseen source.

Commands return exit 0 for success, 2 for invalid/unsupported/blocked operations, and 3 for a failed scheduled verification or a status needing recovery. The optional verification `--out` copies the complete receipt only to an explicitly requested path outside both target and bundle; automatic receipts remain in the private bundle. New commands do not infer network, installation, repository hooks, Git publication, production mutation or runtime-activation scopes from `--approve-execution`.

Use the existing authorized `worktree` command before planning when isolation is needed. Plan against that destination itself; the bundle checks resolved path, device/inode identity and current source. Do not rewrite its root hash to make a source-root plan fit a worktree.

## Runtime ownership and host responsibilities

The generated module exposes `ENABLED = False`. This path calls the original baseline directly and makes no model request. The generated factory keeps `SafeRouter`, expiring exact-runtime receipts, shared `BudgetCoordinator`, stable canary scope, required audit and host policy. The existing `runtime(request)` binding owns one stable router per placement; cooperating placements must reuse the same process-local coordinator. The host retains task completion and must not reset identity/budgets on retries. Closed coordinator tasks suppress new assessment; the host's own gate still decides whether any baseline work is permissible.

The feature switch and runtime mode are separate: setting the switch cannot authorize active behavior. Shadow invokes no treatment handler and preserves the baseline; the post-action recipe's shadow currently performs no assessment because it must not alter the completed baseline result. Active synthetic tests use an explicitly private test receipt helper and a supplied in-process fixture provider; neither appears as an activation bypass in generated code. The probe injects the runtime binding for tests, so it does **not** certify a real application's provider/bootstrap setup. That prerequisite remains a host responsibility and a separate deployment/activation decision.

Read-only callbacks (evidence, registry, validation, gate, checks, observations) must be trusted and genuinely observational. The existing guard must lock the same mutable state/approval/revision consulted by execution. A callback or lock with misleading behavior is not made trustworthy by a source parser. A guard must not suppress exceptions from its body. Native extensions, reflection and deliberately hostile code are outside this verifier's trust boundary; execute them only under independently provided isolation/supervision.

Host return values and original exceptions are preserved on supported default-off/shadow paths. Active finite decisions may intentionally change the result according to the binding. Executor exceptions are not retried or converted into an assertion that an effect was undone. Post-action finishing and child-result finishing receive the real completed outcome. `PartialPlanError.completed_results` and `.failed_step` expose an interrupted multi-step plan without retrying prior effects.

## Bundles, integrity, recovery and evidence

An external private bundle contains `implementation-spec.json`, `reviewed-inventory.json`, `verification-cases.json`, `implementation-plan.json`, the existing exact `patch-plan.json`, `implementation.diff`, a strictly validated implementation manifest, owned-file preimages, a bounded fsynced journal and execution receipts. Full original and applied hashes are separate; original discovery evidence is never overwritten. The engine identity covers installed Python code and JSON contracts. Schema copies, hashes and cross-artifact bindings are checked before writes.

Apply and rollback reuse the protected-path/exact-digest/source-drift/atomic-write engine. An OS-held bundle lock prevents overlapping operations on that bundle. Journaled writes plus preimages handle ordinary exceptions and actual process termination differently. A fresh status inspects bytes and modes; interrupted work is `blocked_recovery`, not “verified.” Recovery rechecks every owned path, restores only matching integration-owned bytes, and refuses concurrent edits. It never runs `git reset`, `git clean`, or overwrites unrelated files. Keep the bundle until rollback and review are complete. A different engine may read it for safe recovery, but new apply/verification require a current matching engine.

`planned`, `applied_unverified`, `verified`, `verification_failed`, `blocked_recovery` and `rolled_back` are computed states, not copied manifest assertions. A second complete application is idempotent. An unchanged failed verification is not silently successful. Linking a file with the legacy `link` command grants no wiring or deployment status.

**Trust boundary:** local hashes detect mismatches but cannot authenticate claims if an adversary edits the bundle and receipts together. Unanchored status is `integrity_consistent_but_unverified`, even when the receipt says passed. To certify the recorded run, the caller must authenticate and supply the exact verification-receipt SHA256 from a trusted external channel. A random digest copied from that same untrusted bundle is not such a channel. `implement-status` never runs target code. Fresh behavioral evidence always requires execution scope.

The verifier executes the actual modified host entry point in a fresh byte-matched source copy under an isolated Python subprocess. Code-owned profiling observes the integration call, pattern handler, effect calls, values, exceptions, state, and selected recipe postconditions. It checks baseline, off, shadow and enabled behavior; keeps failed/timed-out cases in the denominator; and rejects incomplete observations. A Python audit hook denies ordinary socket/subprocess operations in the synthetic probe, but is **not** an OS security sandbox or an adversarial-code attestation service. Additional explicit baseline/modified argv run under the existing authorized runner and require a trusted or externally isolated target environment. Environment filtering and bounded stdout/stderr are also not a sandbox.

All results from this implementation verifier are classified **synthetic**, even when they establish that the actual edited bytes are reached. They are not observed application benefit, calibrated accuracy, paired task success, production readiness, provider integration or deployment permission. Full local receipts and test output may contain sensitive state; never publish them by default. Release evidence includes only deliberately synthetic metadata summaries, never target preimages, raw private source, credentials or raw provider traffic. Earlier `validation/` reports remain identifiable historical release evidence.

## dev2 correctness and receipt compatibility

Host operation exceptions keep their original object/type and pass through the existing guard unchanged. `PolicyBlock` and `UseFallback` raised by an executor are host exceptions, not instructions to invoke the baseline again. Finishing/cleanup errors after an effect propagate; completed effects are not relabeled as pre-execution blocks. Plan preflight blocks after completed steps still retain `PartialPlanError` results. Off/shadow execute the original outside the router-signal catch scope.

The process-local owner registry retains dead weak references as tombstones within its existing 1,024-placement bound. A collected owner does not permit reconstructing a router or coordinator under the same workflow/placement identity. It does not keep the owner alive, grant a distributed quota, authorize a new budget scope, or automatically reset when a task/router closes. A separately reviewed workflow/receipt uses a deliberate new scope; registry exhaustion fails closed.

A seam parameter cannot shadow any required module binding or the original callee. A registry parameter cannot replace an apparent module dictionary, built-in `dict`, or executor symbol. Module-level exception targets, `match` captures, and assignment expressions evaluated when defining module-level functions/classes count as possible rebinding; ambiguous bindings reject before creating a bundle. Defaults, decorators and class bases can change names before a host is called; ordinary function/class-local body assignments are separate scopes. Post-action executor names must resolve to existing module functions, not parameters. These are conservative exclusions, not new whole-program scope/control-flow claims.

Each probe copies only exact plan-matched bytes/modes for its phase, not merely a copy equal to an already-drifted source. Copy failures are failed scheduled cases, not silently omitted work. After all probes and the separately authorized command, the verifier rechecks discovery and every owned file, including generated-file absence in the baseline. New receipts and CLI summaries record `file_identity_valid`; it is optional in schema 1.0 only to read historical receipts, and `false` cannot accompany status `passed`. Engine/source/runtime digests and external receipt provenance still apply. This is not an OS sandbox or authentication of attacker-controlled execution claims.

Install this follow-up's wheel to obtain these runtime corrections. Existing binding specification schema 1.0 and its declared dependency floor remain readable; that old floor is not evidence that an earlier runtime contains these fixes. Re-plan/review when engine digests change. Old receipts are historical, not edited to make them current.
