# Host-owned runtime lifecycle

`HostRuntimeLifecycle` is a process-local startup object for reviewed generated
Python adapters. A reviewed `host_lifecycle` contract for the supported
`module-startup-v1` shape adds named startup, task-completion and shutdown
functions to the edited host module. The application calls those functions;
generated startup constructs the lifecycle and installs its runtime callback
within the edited module. Task completion closes the task after its final
action, and shutdown closes the lifecycle. The callback returns the same
router for each decision. All placements share one `BudgetCoordinator` and one
canary scope. A forked process cannot reuse the object. The exact generated
adapter specification is hashed at startup and checked before each callback.

The supported `module-startup-v1` shape is a flat Python host with a local
top-level runtime binding and reviewed files in both roles: a pinned dependency
lock and an off-mode JSON configuration.
Generated startup requires the exact post-apply paths and SHA-256 hashes from
those reviewed files; a self-consistent substitute dependency plan is refused.
The offline implementation verifier still checks host outcomes, effects and
ordinary global state against baseline. Its parity comparison ignores only the
two generated lifecycle bookkeeping globals while they retain their neutral
pre-start values; a changed value fails parity.

```python
# Edited application's startup path, using the reviewed generated function.
runtime = host_module.start_jev_runtime(
    budget_limits=reviewed_process_limits,
    audit_log=host_audit,
    dependency_plan=reviewed_dependency_file_hashes,
    client=offline_fixture_client,
)
try:
    run_host_task_loop()
    host_module.finish_jev_task(stable_task_id)
finally:
    host_module.stop_jev_runtime()
```

Startup requires an exact dependency plan containing absolute paths and SHA-256
digests of already prepared lock/configuration files. It checks those bytes and
does not install packages. A reviewed implementation specification may include
up to four existing `runtime_files` with `kind` (`configuration` or
`dependency_lock`), an old source hash, and complete new UTF-8 content. Those
paths must appear in `output.permitted_edits` and the reviewed inventory; the
ordinary implementation bundle owns the exact diff, hashes and preimages.
This bounded path supports JSON configuration whose `jev_runtime.mode` stays
`off`, with a credential reference only, and plain pinned `name==version`
lockfiles containing the evaluator. Other config/lock syntaxes are unsupported.
Existing bundle apply authority covers these file edits, and owned rollback
restores their preimages. It does not authorize package installation or
environment preparation. The supplied audit sink must be host owned.

The default startup mode is `off`. `shadow` is allowed only with an offline
synthetic client and `enable_experiment=True` in the explicit startup call.
Off-mode startup can omit `client` and provider credentials; the generated
runtime uses a no-egress placeholder whose evaluation method fails with a
fixed diagnostic. This permits application startup without provider access.
Startup is one-shot per process; shutdown does not reset the budget for a new
startup. The generated startup accepts `connected_config`, `authority`,
`verify_authority`, `current_environment_digest`, and `ledger_path` for
connected modes. The host must pass all five from its trusted startup path.
`connected_config` has exactly `endpoint`, `credential_ref`
(`env:TYPESAFE_API_KEY`), pinned `model` (`jev-1.13.0` in this version),
`environment_digest`, absolute `source_root`, `source_plan` (absolute paths and
current SHA-256 hashes), and per-placement `source_bindings`. Each binding ties
the SPEC's reviewed pre-edit file hash to its applied host file hash and
generated adapter path/hash. The authenticated egress grant covers this entire
mapping. Each connected adapter must be an imported module whose actual
`__file__` path matches the authenticated adapter bytes; a caller-supplied
object with a matching SPEC is insufficient. The existing dependency plan binds the reviewed lock and
configuration files. The host must retain the ledger file and its `.sqlite`
sidecar across restart. The ledger holds hashed task/effect identities, charged
upper bounds, outstanding reservations, and durable revocation. A missing
database, changed scope/limits, unresolved provider reservation or host effect,
or prior revocation prevents a connected restart. Multiprocess use is rejected;
the ledger is one workflow's local durability record, not a distributed quota.

| Requested mode | Required host authority and evidence | Effective behavior |
|---|---|---|
| `off` | None | No provider client or credential required. |
| offline `shadow` | Explicit synthetic client and generated startup `enable_experiment=True` | Baseline effects; offline assessment only. |
| connected `shadow` | Exact, expiring authenticated egress grant; credential reference; pinned endpoint/model; source, environment, dependency and budget identity; durable ledger | Provider assessments remain observational; baseline controls effects. |
| connected `canary` | Connected shadow requirements plus authenticated expiring deployment grant and exact-runtime activation receipt for every placement; recomputed observed all-gate holdouts and paired study for the canary treatment | Stable task cohort determines exposure; host permission is rechecked inside its existing atomic guard before any effect. |
| connected `active` | Same gates, with an active-treatment study and active-specific grants/receipts | Bounded provider proposals may reach the reviewed host executor after the late host gate. |

`authority` contains `egress_grant` and `activation`. The egress grant includes
the connected configuration identities, adapter digest, budget digest, requested
mode, and `issued_at`/`expires_at`. `verify_authority(kind, digest)` is a trusted
host callback that authenticates the *exact* `egress_grant`, `study`,
`deployment_grant`, and every `activation_receipt` digest against independently
retained authorization. A callback that simply trusts caller JSON supplies no
real authority. `current_environment_digest()` must independently recompute
the currently deployed runtime/environment identity, including the credential
generation and relevant provider configuration; returning the configured
digest by echo is insufficient. The TypeSafe client also compares its captured
key against the current process environment before every connected request.
Rotation therefore suspends the runtime; the host must stop and requalify with
new authority, never keep using a client holding the old key. The activation object has one receipt per placement and an
`evidence` object containing `study`, complete `baseline` and `treatment`
rows, `gate_bundle` with raw holdout rows/plans, current reviewed `inventory`,
`expected_study_digest`, and `deployment_grant`. The component recomputes the
study and every gate; a success flag, installer receipt, synthetic data, or a
connectivity probe cannot replace those records. The receipt must bind the
router's exact runtime contract hash, the matching gate holdout digest, study
and deployment identity. The existing router rechecks receipt expiry and host
policy at execution time. The authenticated deployment grant binds exact raw
baseline/treatment, gate-bundle and inventory digests. Source/dependency,
adapter SPEC and environment identities and all grant/receipt digests are
rechecked before and after provider I/O and immediately before host effects.
The final local effect gate is serialized with router suspension and the
durable effect claim. Effect identity uses the reviewed registry action ID,
reviewed binding role, or validated plan-step ID. Aliases of one executor
share an identity, while distinct registered closures remain distinct. A
revoked or expired JEV proposal can fall back to one
host-authorized deterministic baseline effect; a completed task cannot replay.
This local atomic boundary cannot revoke a side effect that already began.
An inherited router or ledger rejects operations after a process fork; the
host must start a new authorized lifecycle in the child.

`HostRuntimeLifecycle.qualification_inputs()` describes the redacted inputs
for an independent live qualification (#57). `mode_status()` reports requested
and effective mode, a fixed rejection reason, configuration digest, owner PID,
placements and shared budget snapshot; it never returns a credential. A
connected host calls `suspend()` or `revoke_activation()` to latch all routers
off and durably block restart. A monitoring hook may only invoke suspension;
it cannot resume exposure. A clean `close()` waits for router workers and
retains charged spend. A restart needs fresh applicable host grants/receipts;
it never replenishes counters for the same ledger scope. The supported upward
transition is a clean shutdown of connected shadow, then a new process startup
with the *same* ledger and a new mode-specific authenticated egress grant plus
all canary/active evidence and receipts. A clean canary-to-active transition
uses the same sequence with an active-treatment study and active grants.
Generated startup is one-shot within a process; there is no in-place promotion.
Off remains credential-free. Suspend/revoke never promotes or resumes: it is
durable and requires separate reconciliation and a newly approved budget scope.
If a provider request
or host effect was pending when the process stopped, preserve the ledger and
reconcile that outcome outside this API before any new exposure. Do not delete
or reset the ledger to bypass this gate.

The old three-field `egress_grant` and exact synthetic connectivity probe
remain available in off mode for compatibility. The probe reports only
reachability and never activates treatment. Connected operation is opt-in and
is not performed by ordinary tests or demos. No real provider, target-native
run, observed benefit, or production authorization is asserted by offline
fixture tests.
The serialized configuration, authority, status and qualification shapes are
versioned in `schemas/host-runtime-connected-v1.schema.json` and mirrored in
the installed package. Python callbacks and external digest provenance are
checked at runtime; the schema alone does not authenticate them.
`connectivity_probe_plan()` describes a fixed synthetic marker request without
egress. A separate exact digest and matching egress grant must be supplied to
`probe_provider_connectivity()`. It makes at most one request per lifecycle,
charges the shared coordinator even on transport failure or deadline, and
returns only a redacted status. This does not grant active treatment or prove
benefit. Do not put key values or raw target requests in config or diagnostics.

The bounded Python recipe C console profile can wire these calls through an
actual reviewed `[project.scripts]` entrypoint; see
[template Python entrypoint v1](template-python-entrypoint-v1.md). Its
two-task loop snapshots unique task IDs before one startup, completes each
after its final effect, and shuts down on success, exception or cancellation.
The original lifecycle tests import the edited synthetic host and call its generated startup,
entrypoint, task-completion and shutdown functions in both off and offline
shadow mode, with no verifier callback replacement.
It also tests lifecycle ownership, task tombstones, cross-thread shared budgets,
dependency drift, reviewed lock/config planning and rollback, and startup
failure. It does not yet prove repository-run
dispatch into an independently reviewed application's startup; issue #6
integration and independent review are required before claiming that condition.
Multiprocess and distributed hosts require a separately qualified coordinator
backend and are rejected. Process-local counters cannot cap deployment-wide
provider spending. Live provider connectivity, native target execution,
observed benefit and activation remain untested. The connectivity path is
exercised only with a mock client in tests.
