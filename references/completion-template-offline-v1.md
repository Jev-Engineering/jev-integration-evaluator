# E completion offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification of
`python.E@1.0` in mode `off`. It uses one reviewed one-argument tail-call seam
in a regular `completion_host` package. The normal installed `completion-host`
console applies a host-approved finite `close_and_label` operation. Its
executor reports `ok`, but the outcome comes from separately read raw state
and effect-receipt files. The [matrix](use-case-template-matrix-v1.md) pins
the unchanged [completion oracle](../examples/coding-agent/completion_oracle.py)
and the [host consumer](../examples/use-case-host/completion_consumer.py) by
byte hash. `inspect_use_case_source(root, "E")` checks both without importing
the host.

## Scoped offline command

Prepare an exact offline wheelhouse outside the checkout with the reviewed
evaluator wheel, its dependency closure and pinned build tools. On Linux
x86-64 CPython 3.13:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_completion_host.py
```

The test creates a new source package, rescans and reviews its E seam, validates
and materializes the template, then plans, baselines, applies and verifies the
generated edit. It checks current implementation status with the modified
receipt digest. The #55 package/install plans bind the full applied tree,
template, exact wheelhouse, build tools and off-mode configuration. Wrong
approvals and changed consumer bytes are refused. The installed metadata
check verifies the exact console module under the owned environment; #55
revalidates the installed distribution RECORD bytes before #56 launch.

The #56 session takes an externally retained install receipt digest and a
fresh observation schedule. `E_RAW_STATE_PATH`, `E_EFFECT_RECEIPT_PATH` and
`E_READY_PATH` are absolute files under a new owner-only `0700` directory
outside the source, package, environment and session trees. The consumer
requires an approved finite operation and fresh unlinked effect paths. It
writes fixture-chosen final state and a fixture-generated receipt with pre/post
hashes using exclusive owner-only files and fsync. The `before` hash comes from
a fixed fixture value; the consumer does not read persisted initial task state.
The test independently computes expected raw bytes, reads both files, and
evaluates final state with the pinned raw oracle. This is a checked fixture
readback, not proof of a real task-state transition or an independent receipt
producer. A success-shaped executor field without the raw goal fails. Missing
permission, an unknown operation or an existing output path refuses a new
effect. An incomplete state/receipt pair cannot satisfy the session's
independent observation schedule and must be reviewed before any retry.

The test disables the first session, builds and installs a separately reviewed
version 1.0.1, stages it with an exact upgrade scope, normally launches and
observes its raw effect, disables it, rolls the session back to the retained
version 1.0.0 generation, and restores both owned source edits. Generation
rollback does not undo a prior task effect. Both
environments remain available for inspection. These are synthetic fixture
versions, not a real application's compatibility guarantee.

## Support boundary

The current #54 console binder accepts recipe C only. This test uses the
reviewed E request and #55 source/install receipts directly, so an E-specific
`template bind` receipt is **pending**. Interrupted upgrade/recovery,
malformed or timed-out provider results, connected authority, a production
host, and measured completion benefit are also pending. The fixture author
controls its finite action and raw state; no model grants permission or adds
attempts. The independent experiment in [#46](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/46)
retains its separate acceptance criteria.
