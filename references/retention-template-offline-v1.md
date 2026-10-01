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

## Quickstart

Ordered commands for a separately reviewed H host with the documented caller
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
jev-integration-evaluator template validate --repo /private/retention-host --request /private/h-request.json

# 2. Bind the reviewed console caller, then materialize planner inputs.
jev-integration-evaluator template bind --repo /private/retention-host --request /private/h-request.json --binding /private/h-binding.json --out /private/h-bound
jev-integration-evaluator template materialize --repo /private/retention-host --request /private/h-bound/template-request.json --out /private/h-render

# 3. Plan, record the baseline, apply the exact bundle and verify it.
jev-integration-evaluator implement-plan --repo /private/retention-host --inventory /private/h-render/reviewed-inventory.json --candidate CANDIDATE_ID --spec /private/h-render/implementation-spec.json --out /private/h-bundle
jev-integration-evaluator implement-verify --phase baseline --repo /private/retention-host --bundle /private/h-bundle --approve-execution
jev-integration-evaluator implement-apply --repo /private/retention-host --bundle /private/h-bundle --approve BUNDLE_DIGEST --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /private/retention-host --bundle /private/h-bundle --approve-execution --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo /private/retention-host --bundle /private/h-bundle --trusted-receipt-sha256 MODIFIED_RECEIPT_SHA256

# 4. Configure and install offline. The package request carries the reviewed
#    off-mode configuration and its independently retained digest.
jev-integration-evaluator template package --request /private/h-package-request.json --out /private/h-package-plan.json
jev-integration-evaluator template package-build --plan /private/h-package-plan.json --approve-plan-sha256 PACKAGE_PLAN_SHA256
jev-integration-evaluator template install-plan --package-plan /private/h-package-plan.json --package-receipt /private/h-package-receipt.json --out /private/h-install-plan.json
jev-integration-evaluator template install --plan /private/h-install-plan.json --approve-plan-sha256 INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/h-install-plan.json

# 5. Normal start of the installed `retention-host` console in mode off, then
#    independent observation and status.
jev-integration-evaluator template delivery-plan --install-plan /private/h-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --observation /private/h-observation.json --launch-environment /private/h-launch-environment.json --out /private/h-delivery-plan.json
jev-integration-evaluator template deploy --session /private/h-session --plan /private/h-delivery-plan.json
jev-integration-evaluator template deploy --session /private/h-session --scope /private/h-launch-scope.json --approve-scope-sha256 LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/h-session --trusted-session-head SESSION_HEAD_SHA256
jev-integration-evaluator template status --session /private/h-session --trusted-session-head SESSION_HEAD_SHA256

# 6. Disable, upgrade to a separately reviewed and installed generation,
#    roll the generation back, then restore the owned source edit.
jev-integration-evaluator template disable --session /private/h-session --scope /private/h-disable-scope.json --approve-scope-sha256 DISABLE_SCOPE_SHA256
jev-integration-evaluator template upgrade --session /private/h-session --plan /private/h-delivery-plan-v2.json --scope /private/h-upgrade-scope.json --approve-scope-sha256 UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/h-session --scope /private/h-rollback-scope.json --approve-scope-sha256 ROLLBACK_SCOPE_SHA256
jev-integration-evaluator implement-rollback --repo /private/retention-host --bundle /private/h-bundle --approve ROLLBACK_DIGEST
```

The upgrade plan in step 6 is a second `template delivery-plan` result for a
second reviewed host version that went through steps 1 to 4 on its own. A
launch after `template upgrade` and the later `template disable` each need a
new exact scope.

Optional offline synthetic connected shadow, with the finite `retention-h-v1`
profile and a host that includes the reviewed `connected_authority.py` loader
before its final scan and binding:

```bash
jev-integration-evaluator template connected-installed-bind --package-plan /private/h-package-plan.json --package-receipt /private/h-package-receipt.json --install-plan /private/h-install-plan.json --install-receipt /private/h-install-receipt.json --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --out /private/h-installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/h-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --installed-binding /private/h-installed-binding.json --trusted-binding-sha256 BINDING_SHA256 --observation /private/h-connected-observation.json --launch-environment /private/h-connected-environment.json --host-profile retention-h-v1 --out /private/h-connected-plan.json
jev-integration-evaluator template connected-configure --session /private/h-connected-session --plan /private/h-connected-plan.json --approve-plan-sha256 CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/h-connected-session --scope /private/h-connected-launch-scope.json --approve-scope-sha256 CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/h-connected-session
jev-integration-evaluator template connected-stop --session /private/h-connected-session --scope /private/h-connected-stop-scope.json --approve-scope-sha256 CONNECTED_STOP_SCOPE_SHA256
```

Connected shadow only observes: the host keeps its deterministic baseline
effect. See the [connected reference](retention-template-connected-v1.md) for the signed
references and the fault schedule. No command here contacts a provider,
enables canary or active mode, or measures benefit.

## Parameters and bindings

A launch environment is a JSON object of string values passed with
`--launch-environment`. `template connected-plan` accepts only the names
listed here for the `retention-h-v1` profile; any other name, including the
supervisor-injected `H_CONNECTED_REF_SHA256` and `H_AUTH_PUBKEY_SHA256`,
is refused with `connected_host_references_required`. These finite controls
select reviewed host schedules; none grants runtime, egress or activation
authority.

| Name | Where | Allowed values | Default | What refuses |
| --- | --- | --- | --- | --- |
| `template_id`, `template_version`, `backend`, `profile` | template request | `python.bounded-tail-call`, `1.0.0`, `python`, `module-tail-call-v1` | none; required | `template validate` rejects any other value or changed source |
| `version` | binding input | `1.0` | none; required | `template bind` rejects the binding |
| `script` | binding input | `retention-host`, a console script declared in `pyproject.toml` | none; required | `Declared console script is absent or ambiguous` |
| `startup_inputs` | binding input | `budget_limits`, `audit_log`, `dependency_plan` and `startup_options`, each naming a zero-argument factory in the console module (`limits`, `audit`, `dependencies`, `options` in the fixture) | none; all four required | `template bind` rejects a missing or drifted factory |
| `configuration`, `reviewed_configuration_sha256` | package request | strict off-mode `{"jev_runtime": {"mode": "off", "credential_ref": null}}` and its digest | none; required | `reviewed_configuration_drift` at package planning; `installed_configuration_drift` at status |
| `console_script` | package request | `retention-host` | none; required | package planning rejects a script the host does not declare |
| `JEV_TEMPLATE_WHEELHOUSE` | test input | absolute private wheelhouse directory | unset | unset: the installed test modules skip, which is not evidence |
| `H_COMMAND` | off-mode and connected launch environment | `/prune` only | none; the explicit user choice is required | `explicit /prune choice required; /compact is separate`; `connected_retention_requires_explicit_prune` at connected planning |
| `H_RETAINED_PATH` | off-mode launch environment | fresh absolute retained-state file under an owner-private directory | none; required for an effect | `H_RETAINED_PATH is required for a retained-state effect`; `retained state path must be fresh, absolute and unlinked` |
| `H_READY_PATH` | off-mode and connected launch environment | fresh absolute ready marker | none; required by the connected profile | `connected_host_references_required` |
| `H_REQUEST_SCENARIO` | off-mode launch environment of the test fixture console | `normal`, `duplicate`, `budget` | `normal` | `duplicate` ends in `duplicate_task_identity`; `budget` in `retention task budget refused`; the connected profile does not accept this name |
| `--host-profile` | `template connected-plan` | `retention-h-v1` | omitted selects the legacy Alpha profile | `connected_host_profile_binding_mismatch` |
| `H_CONNECTED_REF` | connected launch environment | absolute owner-private signed reference file | none; required | `connected_host_references_required`; `connected_private_reference_invalid`; `connected_plan_or_reference_drift` after a change |
| `H_AUTH_PUBKEY_FILE` | connected launch environment | absolute owner-private public-only P-256 key file | none; required | `connected_host_references_required`; a launch scope naming another key hash is `exact_expiring_connected_scope_required` |
| `SSL_CERT_FILE` | connected launch environment | absolute owner-private trust certificate, pinned by hash | unset | `connected_private_reference_invalid` |
| `TYPESAFE_API_KEY` | supervisor process environment at `template connected-launch` | present and non-empty; the value is never written to a plan or log | unset | `connected_credential_unavailable` before any launch attempt |
| `H_EFFECT_DIRECTORY` | connected launch environment | owner-private directory for the per-task retained-state files | none; required | `connected_host_references_required` |
| `H_TASKS` | connected launch environment | `two`, `duplicate` | `two` | `connected_host_references_required`; `duplicate` is refused before an effect |
| `H_HOLD` | connected launch environment | `0`, `1` | `0` | `connected_host_references_required`, also when `1` without `H_RELEASE_PATH` |
| `H_RELEASE_PATH` | connected launch environment | absolute path the operator creates to release a hold | unset | required when `H_HOLD` is `1` |

## Unsupported cases

Each item is refused or left pending by the code and tests named in this
reference; none is silently adapted.

- A console caller that is not a bounded explicit request loop: binding refuses with `bounded explicit request loop`.
- `/compact`, or no explicit choice: `explicit /prune choice required; /compact is separate`. Generative compaction is a separate policy and is never performed by this template; connected planning refuses with `connected_retention_requires_explicit_prune`.
- Dropping a pinned item, changing retained raw bytes or committing over the token budget: `retention postcondition failed`. A changed selected source item: `selected source item changed`. An unknown ID: `unknown retained ID`.
- A token budget outside the reviewed range: `host token budget must be an integer in [0, 6]`.
- An occupied or linked effect path: `retained state path must be fresh, absolute and unlinked`.
- A repeated task ID: `duplicate_task_identity`. More tasks than the reviewed limit: `retention task budget refused`.
- Processing real user history, more than one successful task ID in the off-mode fixture, interruption recovery and measured recall benefit: outside this fixture.
- A requested mode other than shadow at `template connected-plan`: `connected_mode_requires_observed_gate`. Canary and active need separate observed gates.
- A launch environment name or value outside the table above, or a missing required reference: `connected_host_references_required`.
- An installed binding from another host profile: `connected_host_profile_binding_mismatch`.
- A changed reference, source or plan after planning: `connected_plan_or_reference_drift`; a second launch of one session: `connected_launch_already_attempted`.
- Any platform other than Linux x86-64 CPython 3.13 for the installed stages, a missing offline wheelhouse, connected upgrade for this row, provider operation, canary or active mode and measured benefit: not qualified here and recorded as pending.
