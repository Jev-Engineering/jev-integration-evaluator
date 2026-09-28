# Host-owned runtime lifecycle (issue #12 checkpoint)

`HostRuntimeLifecycle` is a process-local startup object for reviewed generated
Python adapters. The application imports its adapter modules, constructs one
lifecycle at startup, installs `runtime_binding(candidate_id)` as each existing
host runtime callback, calls `complete_task(task_id)` only after the whole task
is finished, and calls `close()` at shutdown. The callback returns the same
router for each decision. All placements share one `BudgetCoordinator` and one
canary scope. A forked process cannot reuse the object. The exact generated
adapter specification is hashed at startup and checked before each callback.

```python
# Host-owned startup, after loading reviewed generated adapter modules.
with HostRuntimeLifecycle(
    {adapter.SPEC['candidate_id']: adapter},
    budget_limits=reviewed_process_limits,
    audit_log=host_audit,
    dependency_plan=reviewed_dependency_file_hashes,
    client=offline_fixture_client,
) as runtime:
    host_module.runtime = runtime.runtime_binding(adapter.SPEC['candidate_id'])
    # The application runs its own task loop. The adapter flag remains off
    # until a separately reviewed synthetic experiment deliberately enables it.
    run_host_task_loop()
    runtime.complete_task(stable_task_id)
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
synthetic client; the generated adapter's own `ENABLED` switch remains off until
the host deliberately selects its experimental path. Active and canary startup
are unsupported here. A remote TypeSafe client is created only with an explicit
exact endpoint, `env:TYPESAFE_API_KEY` credential reference and bounded cost
reservation; absent credential or bad endpoint fails with a fixed diagnostic.
`connectivity_probe_plan()` describes a fixed synthetic marker request without
egress. A separate exact digest and matching egress grant must be supplied to
`probe_provider_connectivity()`. It makes at most one request per lifecycle,
charges the shared coordinator even on transport failure or deadline, and
returns only a redacted status. This does not grant active treatment or prove
benefit. Do not put key values or raw target requests in config or diagnostics.

This checkpoint tests a transformed synthetic host through its actual generated
adapter and a startup-installed callback in both off and offline shadow mode.
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
