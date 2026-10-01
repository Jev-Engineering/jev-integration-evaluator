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

## Quickstart

Ordered commands for a separately reviewed E host with the documented caller
grammar, on Linux x86-64 CPython 3.13. Every path is a placeholder for an
owner-private location outside the host checkout. Each command prints a JSON
result; retain the digests it reports outside the directories it wrote and
pass them back wherever an `--approve...` or `--trusted...` flag asks for
one. A digest read back from an untrusted bundle or session is not an
approval. The installed journeys named above drive these stages through the
Python functions each subcommand dispatches to; they do not replay this
transcript. [`tests/test_use_case_template_docs.py`](../tests/test_use_case_template_docs.py)
parses every command below with the real argument parser.

```bash
# 1. Read-only: packaged template, current source and reviewed parameters.
jev-integration-evaluator template inspect python.bounded-tail-call --version 1.0.0
jev-integration-evaluator template validate --repo /private/completion-host --request /private/e-request.json

# 2. Bind the reviewed console caller, then materialize planner inputs.
jev-integration-evaluator template bind --repo /private/completion-host --request /private/e-request.json --binding /private/e-binding.json --out /private/e-bound
jev-integration-evaluator template materialize --repo /private/completion-host --request /private/e-bound/template-request.json --out /private/e-render

# 3. Plan, record the baseline, apply the exact bundle and verify it.
jev-integration-evaluator implement-plan --repo /private/completion-host --inventory /private/e-render/reviewed-inventory.json --candidate CANDIDATE_ID --spec /private/e-render/implementation-spec.json --out /private/e-bundle
jev-integration-evaluator implement-verify --phase baseline --repo /private/completion-host --bundle /private/e-bundle --approve-execution
jev-integration-evaluator implement-apply --repo /private/completion-host --bundle /private/e-bundle --approve BUNDLE_DIGEST --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /private/completion-host --bundle /private/e-bundle --approve-execution --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo /private/completion-host --bundle /private/e-bundle --trusted-receipt-sha256 MODIFIED_RECEIPT_SHA256

# 4. Configure and install offline. The package request carries the reviewed
#    off-mode configuration and its independently retained digest.
jev-integration-evaluator template package --request /private/e-package-request.json --out /private/e-package-plan.json
jev-integration-evaluator template package-build --plan /private/e-package-plan.json --approve-plan-sha256 PACKAGE_PLAN_SHA256
jev-integration-evaluator template install-plan --package-plan /private/e-package-plan.json --package-receipt /private/e-package-receipt.json --out /private/e-install-plan.json
jev-integration-evaluator template install --plan /private/e-install-plan.json --approve-plan-sha256 INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/e-install-plan.json

# 5. Normal start of the installed `completion-host` console in mode off, then
#    independent observation and status.
jev-integration-evaluator template delivery-plan --install-plan /private/e-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --observation /private/e-observation.json --launch-environment /private/e-launch-environment.json --out /private/e-delivery-plan.json
jev-integration-evaluator template deploy --session /private/e-session --plan /private/e-delivery-plan.json
jev-integration-evaluator template deploy --session /private/e-session --scope /private/e-launch-scope.json --approve-scope-sha256 LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/e-session --trusted-session-head SESSION_HEAD_SHA256
jev-integration-evaluator template status --session /private/e-session --trusted-session-head SESSION_HEAD_SHA256

# 6. Disable, upgrade to a separately reviewed and installed generation,
#    roll the generation back, then restore the owned source edit.
jev-integration-evaluator template disable --session /private/e-session --scope /private/e-disable-scope.json --approve-scope-sha256 DISABLE_SCOPE_SHA256
jev-integration-evaluator template upgrade --session /private/e-session --plan /private/e-delivery-plan-v2.json --scope /private/e-upgrade-scope.json --approve-scope-sha256 UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/e-session --scope /private/e-rollback-scope.json --approve-scope-sha256 ROLLBACK_SCOPE_SHA256
jev-integration-evaluator implement-rollback --repo /private/completion-host --bundle /private/e-bundle --approve ROLLBACK_DIGEST
```

The upgrade plan in step 6 is a second `template delivery-plan` result for a
second reviewed host version that went through steps 1 to 4 on its own. A
launch after `template upgrade` and the later `template disable` each need a
new exact scope.

Optional offline synthetic connected shadow, with the finite `completion-e-v1`
profile and a host that includes the reviewed `connected_authority.py` loader
before its final scan and binding:

```bash
jev-integration-evaluator template connected-installed-bind --package-plan /private/e-package-plan.json --package-receipt /private/e-package-receipt.json --install-plan /private/e-install-plan.json --install-receipt /private/e-install-receipt.json --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --out /private/e-installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/e-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --installed-binding /private/e-installed-binding.json --trusted-binding-sha256 BINDING_SHA256 --observation /private/e-connected-observation.json --launch-environment /private/e-connected-environment.json --host-profile completion-e-v1 --out /private/e-connected-plan.json
jev-integration-evaluator template connected-configure --session /private/e-connected-session --plan /private/e-connected-plan.json --approve-plan-sha256 CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/e-connected-session --scope /private/e-connected-launch-scope.json --approve-scope-sha256 CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/e-connected-session
jev-integration-evaluator template connected-stop --session /private/e-connected-session --scope /private/e-connected-stop-scope.json --approve-scope-sha256 CONNECTED_STOP_SCOPE_SHA256
```

Connected shadow only observes: the host keeps its deterministic baseline
effect. See the [connected reference](completion-template-connected-v1.md) for the signed
references and the fault schedule. No command here contacts a provider,
enables canary or active mode, or measures benefit.

## Parameters and bindings

A launch environment is a JSON object of string values passed with
`--launch-environment`. `template connected-plan` accepts only the names
listed here for the `completion-e-v1` profile; any other name, including the
supervisor-injected `E_CONNECTED_REF_SHA256` and `E_AUTH_PUBKEY_SHA256`,
is refused with `connected_host_references_required`. These finite controls
select reviewed host schedules; none grants runtime, egress or activation
authority.

| Name | Where | Allowed values | Default | What refuses |
| --- | --- | --- | --- | --- |
| `template_id`, `template_version`, `backend`, `profile` | template request | `python.bounded-tail-call`, `1.0.0`, `python`, `module-tail-call-v1` | none; required | `template validate` rejects any other value or changed source |
| `version` | binding input | `1.0` | none; required | `template bind` rejects the binding |
| `script` | binding input | `completion-host`, a console script declared in `pyproject.toml` | none; required | `Declared console script is absent or ambiguous` |
| `startup_inputs` | binding input | `budget_limits`, `audit_log`, `dependency_plan` and `startup_options`, each naming a zero-argument factory in the console module (`limits`, `audit`, `dependencies`, `options` in the fixture) | none; all four required | `template bind` rejects a missing or drifted factory |
| `configuration`, `reviewed_configuration_sha256` | package request | strict off-mode `{"jev_runtime": {"mode": "off", "credential_ref": null}}` and its digest | none; required | `reviewed_configuration_drift` at package planning; `installed_configuration_drift` at status |
| `console_script` | package request | `completion-host` | none; required | package planning rejects a script the host does not declare |
| `JEV_TEMPLATE_WHEELHOUSE` | test input | absolute private wheelhouse directory | unset | unset: the installed test modules skip, which is not evidence |
| `E_RAW_STATE_PATH` | off-mode launch environment | fresh absolute raw-state file under an owner-private directory | none; required by the consumer unless a template is set | a missing value is refused by name; `completion effect path must be fresh and unlinked` |
| `E_EFFECT_RECEIPT_PATH` | off-mode launch environment | fresh absolute receipt file, distinct from the raw-state file | none; required by the consumer unless a template is set | `completion effects must use distinct private files` |
| `E_READY_PATH` | off-mode and connected launch environment | fresh absolute ready marker | unset: no marker | `connected_host_references_required` for an unlisted name |
| `E_RAW_STATE_TEMPLATE` | off-mode and connected launch environment of the bound task-loop host | absolute path containing `{task_id}`; one raw-state file per task | unset | the derived path must still be fresh and owner-private |
| `E_EFFECT_RECEIPT_TEMPLATE` | off-mode and connected launch environment of the bound task-loop host | absolute path containing `{task_id}`; one receipt file per task | unset | the derived path must still be fresh and owner-private |
| `--host-profile` | `template connected-plan` | `completion-e-v1` | omitted selects the legacy Alpha profile | `connected_host_profile_binding_mismatch` |
| `E_CONNECTED_REF` | connected launch environment | absolute owner-private signed reference file | none; required | `connected_host_references_required`; `connected_private_reference_invalid`; `connected_plan_or_reference_drift` after a change |
| `E_AUTH_PUBKEY_FILE` | connected launch environment | absolute owner-private public-only P-256 key file | none; required | `connected_host_references_required`; a launch scope naming another key hash is `exact_expiring_connected_scope_required` |
| `SSL_CERT_FILE` | connected launch environment | absolute owner-private trust certificate, pinned by hash | unset | `connected_private_reference_invalid` |
| `TYPESAFE_API_KEY` | supervisor process environment at `template connected-launch` | present and non-empty; the value is never written to a plan or log | unset | `connected_credential_unavailable` before any launch attempt |
| `E_TASKS` | connected launch environment | `two`, `duplicate` | `two` | `connected_host_references_required`; `duplicate` is refused before replaying an effect |

## Unsupported cases

Each item is refused or left pending by the code and tests named in this
reference; none is silently adapted.

- A console caller outside the reviewed task-loop shape, including the single-request return form, decorators, dynamic imports and extra calls in the loop: binding refuses with `bounded task loop`.
- An operation other than the host-approved `close_and_label`, or a denied host permission: `completion host permission or operation refused`.
- Occupied, linked or shared effect files: `completion effect path must be fresh and unlinked`; `completion effects must use distinct private files`.
- Treating an executor success report as completion: the independent raw-state and receipt oracle decides, and a false completion is scored as failure.
- A repeated task ID or a schedule above the 32-task bound: refused before startup.
- A changed installed generation: `installed_generation_drift_or_unverified`.
- Extra actions or attempts granted by an assessment, interrupted upgrade recovery and a production host: outside this fixture.
- A requested mode other than shadow at `template connected-plan`: `connected_mode_requires_observed_gate`. Canary and active need separate observed gates.
- A launch environment name or value outside the table above, or a missing required reference: `connected_host_references_required`.
- An installed binding from another host profile: `connected_host_profile_binding_mismatch`.
- A changed reference, source or plan after planning: `connected_plan_or_reference_drift`; a second launch of one session: `connected_launch_already_attempted`.
- Any platform other than Linux x86-64 CPython 3.13 for the installed stages, a missing offline wheelhouse, connected upgrade for this row, provider operation, canary or active mode and measured benefit: not qualified here and recorded as pending.
