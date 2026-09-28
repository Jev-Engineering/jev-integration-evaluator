# Host-owned runtime lifecycle (issue #12 checkpoint)

`HostRuntimeLifecycle` is a process-local startup object for reviewed generated
Python adapters. The application imports its adapter modules, constructs one
lifecycle at startup, installs `runtime_binding(candidate_id)` as each existing
host runtime callback, calls `complete_task(task_id)` only after the whole task
is finished, and calls `close()` at shutdown. The callback returns the same
router for each decision. All placements share one `BudgetCoordinator` and one
canary scope. A forked process cannot reuse the object.

Startup requires an exact dependency plan containing absolute paths and SHA-256
digests of already prepared lock/configuration files. It checks those bytes and
does not install packages. The eventual implementation bundle must own any
dependency or configuration edits separately; this runtime check is not an
installation or mutation grant. The supplied audit sink must be host owned.

The default startup mode is `off`. `shadow` is allowed only with an offline
synthetic client; the generated adapter's own `ENABLED` switch remains off until
the host deliberately selects its experimental path. Active and canary startup
are unsupported here. A remote TypeSafe client is created only with an explicit
exact endpoint and `env:TYPESAFE_API_KEY` credential reference; absent credential
or bad endpoint fails with a fixed diagnostic. This does not grant active
treatment. Do not put key values or raw requests in config or diagnostics.

This checkpoint tests lifecycle ownership, task tombstones, shared budgets,
dependency drift and startup failure offline. It does not yet prove repository
run dispatch into a real application's startup; issue #6 integration and an
independent review are required before claiming that acceptance condition.
Multiprocess and distributed hosts require a separately qualified coordinator
backend and are rejected. Process-local counters cannot cap deployment-wide
provider spending. Provider connectivity, native target execution, observed
benefit and activation remain untested.
