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
  python3.13 -m pytest -q tests/test_use_case_retention_host.py
```

The launch environment supplies `H_RETAINED_PATH` and `H_READY_PATH` as fresh
absolute paths outside the source, package, environment and session trees.
The retained-state parent must be owner-private `0700`. The consumer accepts
only the exact reviewed selected item records and explicit `/prune`; it checks
pins, raw bytes/provenance and a six-token budget before an exclusive write.
The observer independently computes the expected file bytes and reads the raw
items after launch. It separately scores later recall from that readback. The
installed off-mode fallback retains all three items; a separate consumer case
shows `/prune` can drop the reviewed unpinned item. It never treats a host
`success` field as the outcome.

`/compact`, changed selected source items, missing pins, reused output paths,
source drift, unapproved package/install plans and non-off mode are unsupported
or rejected. The #54 console binder currently accepts recipe C only; this H
journey uses source-tree and entrypoint binding from the validated H request
and #55 package/install receipts, without claiming a #54 H bind report.
The test installs a second reviewed host version (1.0.1), stops the first,
stages the new generation with an exact upgrade scope, launches and observes
its raw effect, then disables it and rolls back to the retained first
generation. Both installed environments remain for review; the two owned
source edits are restored separately. Interrupted upgrade/recovery, connected
authority, provider responses and task-level retention benefit remain pending.
