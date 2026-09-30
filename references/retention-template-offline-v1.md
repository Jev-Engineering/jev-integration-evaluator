# H retention offline host: operator reference

This is an executable **synthetic** host qualification for recipe `python.H@1.0`
on Linux x86-64 CPython 3.13. It exercises only mode `off`, a finite `/prune`
choice and a fresh external retained-state file. It does not process user
history, perform `/compact`, call a provider or establish measured benefit.

The source contract pins the unchanged
[`retention_oracle.py`](../examples/coding-agent/retention_oracle.py) and
[`retention_consumer.py`](../examples/use-case-host/retention_consumer.py) bytes
in the [six-row matrix](../jev_integration_evaluator/data/use-case-template-matrix-v1.json).
`inspect_use_case_source(root, "H")` checks both without importing target code.
The test builder creates a separate regular package with one reviewed H
tail-call seam and a normal `retention-host` console. It rescans and reviews
that host before `validate_template_request` and `materialize_template`, then
uses `plan_implementation`, baseline verification, `apply_implementation` and
modified verification. The exact applied source tree, materialized template,
external modified receipt digest, pinned interpreter/build tools/wheels,
off-mode configuration and console name feed `plan_package` and `plan_install`.
An external install receipt digest feeds `plan_delivery`; a separate expiring
operator scope authorizes launch, disable, exact versioned upgrade and rollback.

Run the focused offline journey only with a previously prepared wheelhouse:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/owner-private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_retention_host.py \
    tests/test_use_case_retention_bind.py \
    tests/test_use_case_retention_bound_installed.py
```

For a separately reviewed H package with the documented caller grammar, use
this explicit binding input outside the target:

```json
{"version":"1.0","script":"retention-host","startup_inputs":{"budget_limits":"limits","audit_log":"audit","dependency_plan":"dependencies","startup_options":"options"}}
```

```bash
jev-integration-evaluator template bind --repo /private/retention-host \
  --request /private/h-request.json --binding /private/h-binding.json \
  --out /private/h-bound
jev-integration-evaluator template materialize --repo /private/retention-host \
  --request /private/h-bound/template-request.json --out /private/h-render
```

Review and retain `binding-report.json`, the bound request, current source
hashes and the separate implementation/package/install receipts. Binding is
read-only. The H console profile uses a regular package and a bounded loop
that passes each unchanged request once to the reviewed H seam. The fixture
supplies exactly one task and requires an explicit `H_COMMAND=/prune` at normal
console invocation. Missing choice and `/compact` refuse before a retained
state effect. The generated console starts one process-local runtime, completes
the task and shuts down in `finally`. The bound installed check verifies the
normal console's installed origin, raw retained bytes, pinned provenance and
owned source rollback. The [bound installed journey](../tests/test_use_case_retention_bound_installed.py)
carries that same reviewed binder through #55 package/install and #56
supervised normal launch, status, disable, reviewed 1.0.1 upgrade and retained
1.0.0 generation rollback. It checks raw retained items and later recall from
the installed effect. Duplicate task IDs, a request count beyond the host
limit, missing choice, `/compact` and an occupied effect path refuse without
a new retained-state effect. The existing unbound supervised journey remains
a separate fixture and retains its prior evidence.

The launch environment supplies `H_RETAINED_PATH` and `H_READY_PATH` as fresh
absolute paths outside the source, package, environment and session trees.
The retained-state parent must be owner-private `0700`. The consumer accepts
only the exact reviewed selected item records and explicit `/prune`; it checks
pins, raw bytes/provenance and the host's finite token budget before an exclusive
write. A missing or empty `H_RETAINED_PATH` refuses the commit. The isolated
synthetic verifier supplies a `retained-{pid}.json` path under a private
directory so each subprocess writes a distinct raw effect; the installed
launch uses one exact path. The installed host budget is six tokens, while a
separate direct consumer test lowers that host input to four and verifies that
retaining all three items is refused without writing a file.
The observer independently computes the expected file bytes and reads the raw
items after launch. It separately scores later recall from that readback. The
installed off-mode fallback retains all three items; a separate consumer case
shows `/prune` can drop the reviewed unpinned item. It never treats a host
`success` field as the outcome.

`/compact`, changed selected source items, missing pins, reused output paths,
source drift, unapproved package/install plans and non-off mode are unsupported
or rejected. The existing supervised H journey uses source-tree and entrypoint
binding from the validated H request and #55 package/install receipts. The
bound H journey has an actual `template bind` report and owned console edit
through the #54 API, carried into its own supervised installed session.
The test installs a second reviewed host version (1.0.1), stops the first,
stages the new generation with an exact upgrade scope, launches and observes
its raw effect, then disables it and rolls back to the retained first
generation. Both installed environments remain for review; the two owned
source edits are restored separately. Interrupted upgrade/recovery, connected
authority, provider responses and task-level retention benefit remain pending.
