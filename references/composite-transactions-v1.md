# Reviewed composite implementation transaction v1

## Installed two-console profile

A narrow additional profile binds two independently reviewed recipe-C console
placements in one Python package. Both declared scripts must be different
functions in the same console source; their host modules and generated adapters
must be distinct, and the current source must match both entrypoint bindings.
The primary script calls both original finite host task functions with one
stable task ID. One `HostRuntimeLifecycle` supplies both bindings and a shared
coordinator; the generated console checks the reviewed per-task budget and
combined dependency hashes before binding either host. The host must supply
`observe_composite_runtime(runtime, request, candidate_ids)` to check actual
audit and effect state. The second task's failure propagates; the first task
is not retried. Planning only reads source and never imports target modules.

The source plan includes `composite-console.json` and its exact rendered file
hash. The composite package/install APIs in
`jev_integration_evaluator.template_installation` accept a distinct
`template-composite-package-request-v1` with both candidate/template locks,
the composite bundle digest and an independently trusted modified verification
receipt. Their separate plan/receipt schemas bind the selected set. Build and
install use the same offline, private generation journal as the single-host
installer; `recover_composite_installation` rechecks that journal and bytes
before adoption or removal. A real installed console is tested on Linux
x86-64 CPython 3.13 with synthetic local effects. Connected composite mode is
unsupported, and installation alone does not establish launch readiness,
provider reachability or benefit. The installed lifecycle supervisor belongs
to issue #56.

The independent #57 dual registered-action fixture in
`tests/independent_hosts/registered_dual` freezes two source-reviewed recipe C
seams and a separate raw-effect oracle. Its opt-in Linux CPython 3.13 driver
uses this composite transaction, the offline package/install APIs and one #56
journey. A normal installed console reaches both transformed seams with one
task ID and one coordinator; its two JSONL effects are checked outside the
host audit. Calls through both seams again during the live owner consume no
additional assessment and the host ledgers refuse duplicate effects. The
driver also reconciles an unreleased start under the same run, disables, and
restores owned source bytes. `JEV_RUNTIME_MODE` stays off; the code-owned
synthetic shadow is offline and supplies no provider or release authority.
This is one package and one process-local owner, not a distributed budget
between the separately installed Alpha and work-queue applications.

`implement-composite-*` is an additive synthetic, trusted-host workflow for two
to four bounded Python recipes. It does not change the original single-placement
CLI, its receipts, or its source-drift rules. The planner reads one reviewed
inventory and a sorted selected candidate set. Every member specification must
name that exact inventory, source hash, experiment, current semantic review and
independent binding review. The selected dependency graph, conflicts, common
task field, policy version, canary scope and per-task call/cost limits join the
selected-set digest. Conflicts, missing dependencies, cycles, and mismatched
runtime ownership are refused before creating a bundle.

The planner transforms every member against the **same untouched repository
snapshot**. Different-file edits are collected once. Two same-file Python edits
are admitted only when each changes one distinct top-level function and inserts
one complete static generated-adapter import; the remaining bytes must be
identical to the original source. Both imports appear once in the final AST.
Changed same-function spans, extra insertion statements, adapter path clashes,
runtime-file differences, and host-lifecycle additions on a shared file fail with
candidate and path diagnostics. The one combined patch and its full-source
inventory, specifications, derived manifests, preimages and selected graph are
sealed under a single bundle digest outside the target.

```bash
jev-integration-evaluator implement-composite-plan --repo TARGET --inventory REVIEWED.json --selection SELECTION.json --specs SPECS-BY-CANDIDATE.json --out NEW_PRIVATE_BUNDLE
jev-integration-evaluator implement-composite-verify --phase baseline --repo TARGET --bundle PRIVATE_BUNDLE --approve-execution
jev-integration-evaluator implement-composite-apply --repo TARGET --bundle PRIVATE_BUNDLE --approve EXACT_BUNDLE_DIGEST --baseline-sha256 EXTERNALLY_RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-composite-verify --phase modified --repo TARGET --bundle PRIVATE_BUNDLE --approve-execution --baseline-sha256 EXTERNALLY_RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-composite-status --repo TARGET --bundle PRIVATE_BUNDLE --trusted-receipt-sha256 EXTERNALLY_AUTHENTICATED_MODIFIED_RECEIPT_SHA256
jev-integration-evaluator implement-composite-rollback --repo TARGET --bundle PRIVATE_BUNDLE --approve EXACT_ROLLBACK_DIGEST
```

`specs` is a JSON object keyed by the selected candidate IDs. See
`examples/implementation/composite-selection.example.json` for the selection
shape; its synthetic IDs and command are examples, not an approved host. Planning
does not import or execute target modules. Execution commands require a separate
trusted synthetic test scope; environment filtering and subprocess probes are
not an operating-system sandbox. Do not use this path for private or untrusted
targets without an independently qualified isolated runner and authority.

Apply holds both the bundle lock and an OS-held lock keyed to the resolved
worktree device/inode/path. Legacy, adaptation and composite operations use this
lock, so separately prepared bundles cannot mutate the same worktree at once.
Before every write, apply rechecks the complete reviewed discovery set and every
owned old hash. It fsyncs preimages and a chained event journal. A crash before
terminal completion leaves `blocked_recovery`; the exact separately approved
rollback restores only matching owned bytes and refuses concurrent edits.
Unrelated files are not overwritten. A completed second apply is idempotent.

Baseline and modified receipts retain **all** scheduled candidate/case/mode
rows, including failures and not-run cases. A baseline receipt is bound to its
planned or rolled-back journal generation. A modified receipt is bound to the
current completed apply generation, so a verified receipt from an earlier
apply cannot verify a rollback/reapply. Status recomputes owned bytes and modes
without running target code; a locally consistent receipt is only
`integrity_consistent_but_unverified` until its digest is independently
authenticated outside the bundle. A stale-generation receipt remains
`applied_unverified` after reapply.

Modified verification probes every member in off, shadow and active synthetic
modes, checks independent declared results/effects and off/shadow parity, then
runs the separately reviewed combined host command. That command must emit one
JSON `composite-host-observation-v1` object with both candidate IDs and expected
results, one task ID, the same process-local coordinator identity and canary
scope for every member, complete audit candidate IDs, and call/cost totals within
the selected shared limits. The inspector retains only a digest of command
stdout and bounded normalized checks. This synthetic contract depends on a
trusted, independently authored host command; self-reported fields alone do not
qualify production behavior. A combined fixture uses the actual
`HostRuntimeLifecycle` and `BudgetCoordinator`, calls both selected host paths,
and verifies a third reservation is denied by the shared limit.

The qualified source shape remains the original bounded module tail call and
the separately versioned method/async adaptation shapes from issue #11; this
transaction composes the original recipe transforms only. It does not support
arbitrary rewrites, distributed budgets, provider activation or deployment.
