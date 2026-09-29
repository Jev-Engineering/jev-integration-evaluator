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

For a separately reviewed E host with the same grammar, retain the current
`template-request-v1` and use this exact binding input outside the target:

```json
{"version":"1.0","script":"completion-host","startup_inputs":{"budget_limits":"limits","audit_log":"audit","dependency_plan":"dependencies","startup_options":"options"}}
```

```bash
jev-integration-evaluator template bind --repo /private/completion-host \
  --request /private/e-request.json --binding /private/e-binding.json \
  --out /private/e-bound
jev-integration-evaluator template materialize --repo /private/completion-host \
  --request /private/e-bound/template-request.json --out /private/e-render
```

Review and retain `binding-report.json` and the derived request digest before
the separately approved implementation, package, install and session stages.
The test's fixture builds those later exact plans and receipts through the
same public APIs; the binding step alone grants no effect or provider access.

The test creates a new source package, rescans and reviews its E seam, then
uses `template bind` to derive a source-bound task-loop caller and own its
console edit. It validates and materializes the bound template, then plans,
baselines, applies and verifies the generated host and console edits. It checks
current implementation status with the modified
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

The #54 console binder now accepts this package-bound E task-loop shape: one
local zero-argument request factory returns a bounded list of dictionaries;
the loop calls the imported one-argument host task, which directly returns
the reviewed E seam, then the console returns zero. The four reviewed startup
factories, lock and off configuration are source-bound. The generated caller
starts one process-local runtime, completes the captured task ID after its
effect, and shuts down in `finally`. The E single-request return form,
decorators, dynamic imports and extra calls in the loop remain unsupported.
The focused E loop check binds two distinct requests to one runtime owner and
checks each raw state and effect receipt with the independent completion oracle.
Duplicate task IDs and schedules above the 32-task bound fail before startup.
This two-request check exercises the applied source; the installed console
journey above uses one request.
The existing `python.bounded-tail-call@1.0.0` catalog manifest keeps its
conservative C binding capability string; this E extension is reported by its
fresh binding report and the E matrix row. Earlier C render locks and receipts
remain historical evidence and require current engine/source validation before
reuse; unchanged manifest bytes alone do not establish replay compatibility.
The fixture action writes the raw state and receipt before its separate ready
marker and bounded observation hold. The host's `ok` report cannot replace
the independent raw oracle. Interrupted upgrade/recovery,
malformed or timed-out provider results, connected authority, a production
host, and measured completion benefit are also pending. The fixture author
controls its finite action and raw state; no model grants permission or adds
attempts. The independent experiment in [#46](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/46)
retains its separate acceptance criteria.
