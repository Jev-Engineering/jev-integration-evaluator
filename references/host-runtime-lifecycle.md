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
startup. Active and canary startup
are unsupported here. A remote TypeSafe client is created only with an explicit
exact endpoint, `env:TYPESAFE_API_KEY` credential reference and bounded cost
reservation; absent credential or bad endpoint fails with a fixed diagnostic.
`connectivity_probe_plan()` describes a fixed synthetic marker request without
egress. A separate exact digest and matching egress grant must be supplied to
`probe_provider_connectivity()`. It makes at most one request per lifecycle,
charges the shared coordinator even on transport failure or deadline, and
returns only a redacted status. This does not grant active treatment or prove
benefit. Do not put key values or raw target requests in config or diagnostics.

The tests import the edited synthetic host and call its generated startup,
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
