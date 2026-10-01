# M claim support offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification of
`python.M@1.0` in mode `off`. A fresh regular `claim_host` package copies the
matrix-pinned RAG claim reviewer and the independently authored consumer by
exact hash. Its reviewed single tail-call seam is planned, baselined, applied,
verified, packaged and installed through the normal template APIs. The
installed `claim-host` console calls that seam and applies only the fixture's
finite, code-owned support rule. The off-mode decision is `inspect`; it grants
no provider or production release authority.

## Scoped offline command

Prepare a private offline wheelhouse containing the exact evaluator wheel,
dependency closure and pinned build tools. On Linux x86-64 CPython 3.13:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_claim_host.py \
    tests/test_use_case_claim_bind.py \
    tests/test_use_case_claim_bound_installed.py
```

The test checks template validation and materialization, #54 source planning,
baseline, apply and modified receipts; #55 package and install plans; and a #56
session with a normal installed console. The package plan binds the entire
reviewed applied tree, so changed claim consumer or oracle bytes refuse before
build. The install and delivery plans bind exact wheelhouse, interpreter,
configuration, install receipt and off-mode launch environment. Wrong scope
digest refuses launch before any effect.

`M_SUPPORT_PATH`, `M_AUDIT_PATH`, `M_CLAIM_PATH` and `M_READY_PATH` point to fresh
external files under one owner-only `0700` directory. The consumer requires a
host-approved finite task. It rejects unsupported critical claims, missing or
partial citations, changed quotes, unknown task IDs and occupied effect paths.
Its finite fixture draft generator has five registered cases: `accept`,
`revise`, `request_evidence`, `fabricated`, and `partial`. The code-owned
assessor supports only `Permit is active` from the fixed
`fixture-permit-register-v1` passage and exact citation offsets. The claim
reviewer blocks fabricated or partial critical citations, requests more
evidence for an uncertain critical claim, and removes an unsupported
noncritical claim under its dependency policy. A revised answer releases only
the supported critical assertion and records the removed claim ID. No model
label or `reported` value grants release authority.

The consumer requires host approval before assessment. It writes support and
audit as exclusive `0600` files with fsync, reopens both with `O_NOFOLLOW`,
checks owner, mode, and exact raw bytes, and only then writes and reads back the
release effect. Support records retain source, passage, span, quote, and exact
citation offsets; the release hashes bind the observed support and audit. A
failed readback leaves no release file. A partial file set remains occupied and
requires external review; no retry is authorized by a reported `ok` value.

The test independently computes expected raw support, audit and release bytes,
reads the installed consumer's files, and verifies the effect hashes reference
the observed support and audit. The supervisor observes distinct ready,
support, audit and release roles. These records are fixture-authored and
synthetic; they are not a provider result or an independent real permit
register. A successful installed `accept` invocation is disabled; a separately
reviewed 1.0.1 fixture package generates `revise`, removes one unsupported
noncritical claim, and is installed and staged through exact upgrade scope,
normally launched and observed, then disabled. Source-level negative tests
cover `request_evidence`, fabricated and partial citations, denied approval,
and corrupted support readback before release. Session rollback selects the
retained 1.0.0 generation. Both source edits are separately rolled back.
Rollback does not erase prior claim effects.

## Support boundary

The #54 console binder accepts a separately reviewed M bounded task loop.
The [bound installed journey](../tests/test_use_case_claim_bound_installed.py)
derives a fresh binding, carries its owned edit through materialization,
baseline, apply, modified verification, #55 offline installation and a normal
installed #56 console session. Independent raw reads check supported citation,
audit and release hashes. The binder rejects duplicate IDs before an effect;
the authored host refuses a task count above its limit; the pinned consumer
blocks fabricated and partial critical citations. A reviewed 1.0.1 package
revises away an unsupported noncritical claim, then the session selects its
retained 1.0.0 generation and both source edits are rolled back. The pinned
consumer accepts only one fixed successful task ID, so this does not qualify
multiple successful task IDs or shared provider spending. The fixture
provides its own fixed passage and finite assertion. Connected assessment,
real citation retrieval, host production audit, benefit, and interrupted
install/upgrade recovery are pending. No model label can authorize a release.

## Quickstart

Ordered commands for a separately reviewed M host with the documented caller
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
jev-integration-evaluator template validate --repo /private/claim-host --request /private/m-request.json

# 2. Bind the reviewed console caller, then materialize planner inputs.
jev-integration-evaluator template bind --repo /private/claim-host --request /private/m-request.json --binding /private/m-binding.json --out /private/m-bound
jev-integration-evaluator template materialize --repo /private/claim-host --request /private/m-bound/template-request.json --out /private/m-render

# 3. Plan, record the baseline, apply the exact bundle and verify it.
jev-integration-evaluator implement-plan --repo /private/claim-host --inventory /private/m-render/reviewed-inventory.json --candidate CANDIDATE_ID --spec /private/m-render/implementation-spec.json --out /private/m-bundle
jev-integration-evaluator implement-verify --phase baseline --repo /private/claim-host --bundle /private/m-bundle --approve-execution
jev-integration-evaluator implement-apply --repo /private/claim-host --bundle /private/m-bundle --approve BUNDLE_DIGEST --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /private/claim-host --bundle /private/m-bundle --approve-execution --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo /private/claim-host --bundle /private/m-bundle --trusted-receipt-sha256 MODIFIED_RECEIPT_SHA256

# 4. Configure and install offline. The package request carries the reviewed
#    off-mode configuration and its independently retained digest.
jev-integration-evaluator template package --request /private/m-package-request.json --out /private/m-package-plan.json
jev-integration-evaluator template package-build --plan /private/m-package-plan.json --approve-plan-sha256 PACKAGE_PLAN_SHA256
jev-integration-evaluator template install-plan --package-plan /private/m-package-plan.json --package-receipt /private/m-package-receipt.json --out /private/m-install-plan.json
jev-integration-evaluator template install --plan /private/m-install-plan.json --approve-plan-sha256 INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/m-install-plan.json

# 5. Normal start of the installed `claim-host` console in mode off, then
#    independent observation and status.
jev-integration-evaluator template delivery-plan --install-plan /private/m-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --observation /private/m-observation.json --launch-environment /private/m-launch-environment.json --out /private/m-delivery-plan.json
jev-integration-evaluator template deploy --session /private/m-session --plan /private/m-delivery-plan.json
jev-integration-evaluator template deploy --session /private/m-session --scope /private/m-launch-scope.json --approve-scope-sha256 LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/m-session --trusted-session-head SESSION_HEAD_SHA256
jev-integration-evaluator template status --session /private/m-session --trusted-session-head SESSION_HEAD_SHA256

# 6. Disable, upgrade to a separately reviewed and installed generation,
#    roll the generation back, then restore the owned source edit.
jev-integration-evaluator template disable --session /private/m-session --scope /private/m-disable-scope.json --approve-scope-sha256 DISABLE_SCOPE_SHA256
jev-integration-evaluator template upgrade --session /private/m-session --plan /private/m-delivery-plan-v2.json --scope /private/m-upgrade-scope.json --approve-scope-sha256 UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/m-session --scope /private/m-rollback-scope.json --approve-scope-sha256 ROLLBACK_SCOPE_SHA256
jev-integration-evaluator implement-rollback --repo /private/claim-host --bundle /private/m-bundle --approve ROLLBACK_DIGEST
```

The upgrade plan in step 6 is a second `template delivery-plan` result for a
second reviewed host version that went through steps 1 to 4 on its own. A
launch after `template upgrade` and the later `template disable` each need a
new exact scope.

Optional offline synthetic connected shadow, with the finite `claim-m-v1`
profile and a host that includes the reviewed `connected_authority.py` loader
before its final scan and binding:

```bash
jev-integration-evaluator template connected-installed-bind --package-plan /private/m-package-plan.json --package-receipt /private/m-package-receipt.json --install-plan /private/m-install-plan.json --install-receipt /private/m-install-receipt.json --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --out /private/m-installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/m-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --installed-binding /private/m-installed-binding.json --trusted-binding-sha256 BINDING_SHA256 --observation /private/m-connected-observation.json --launch-environment /private/m-connected-environment.json --host-profile claim-m-v1 --out /private/m-connected-plan.json
jev-integration-evaluator template connected-configure --session /private/m-connected-session --plan /private/m-connected-plan.json --approve-plan-sha256 CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/m-connected-session --scope /private/m-connected-launch-scope.json --approve-scope-sha256 CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/m-connected-session
jev-integration-evaluator template connected-stop --session /private/m-connected-session --scope /private/m-connected-stop-scope.json --approve-scope-sha256 CONNECTED_STOP_SCOPE_SHA256
```

Connected shadow only observes: the host keeps its deterministic baseline
effect. See the [connected reference](template-claim-connected-v1.md) for the signed
references and the fault schedule. No command here contacts a provider,
enables canary or active mode, or measures benefit.

## Parameters and bindings

A launch environment is a JSON object of string values passed with
`--launch-environment`. `template connected-plan` accepts only the names
listed here for the `claim-m-v1` profile; any other name, including the
supervisor-injected `M_CONNECTED_REF_SHA256` and `M_AUTH_PUBKEY_SHA256`,
is refused with `connected_host_references_required`. These finite controls
select reviewed host schedules; none grants runtime, egress or activation
authority.

| Name | Where | Allowed values | Default | What refuses |
| --- | --- | --- | --- | --- |
| `template_id`, `template_version`, `backend`, `profile` | template request | `python.bounded-tail-call`, `1.0.0`, `python`, `module-tail-call-v1` | none; required | `template validate` rejects any other value or changed source |
| `version` | binding input | `1.0` | none; required | `template bind` rejects the binding |
| `script` | binding input | `claim-host`, a console script declared in `pyproject.toml` | none; required | `Declared console script is absent or ambiguous` |
| `startup_inputs` | binding input | `budget_limits`, `audit_log`, `dependency_plan` and `startup_options`, each naming a zero-argument factory in the console module (`limits`, `audit`, `dependencies`, `options` in the fixture) | none; all four required | `template bind` rejects a missing or drifted factory |
| `configuration`, `reviewed_configuration_sha256` | package request | strict off-mode `{"jev_runtime": {"mode": "off", "credential_ref": null}}` and its digest | none; required | `reviewed_configuration_drift` at package planning; `installed_configuration_drift` at status |
| `console_script` | package request | `claim-host` | none; required | package planning rejects a script the host does not declare |
| `JEV_TEMPLATE_WHEELHOUSE` | test input | absolute private wheelhouse directory | unset | unset: the installed test modules skip, which is not evidence |
| `M_SUPPORT_PATH` | off-mode launch environment | fresh absolute support record under an owner-private directory | none; required | a missing value is refused by name; `claim effect path must be fresh and unlinked` |
| `M_AUDIT_PATH` | off-mode launch environment | fresh absolute audit record, distinct from the other two files | none; required | `claim effects require distinct private files` |
| `M_CLAIM_PATH` | off-mode launch environment | fresh absolute release record, distinct from the other two files | none; required | `claim effects require distinct private files` |
| `M_CLAIM_SCENARIO` | off-mode and connected launch environment | connected profile: `accept`, `revise`, `request_evidence`, `fabricated`, `partial` | `accept` in the connected console | `connected_host_references_required` for any other value; `fabricated` and `partial` end in `critical claim unsupported or citation invalid` with no effect |
| `M_READY_PATH` | off-mode and connected launch environment | fresh absolute ready marker | none; required by the connected profile | `connected_host_references_required` |
| `--host-profile` | `template connected-plan` | `claim-m-v1` | omitted selects the legacy Alpha profile | `connected_host_profile_binding_mismatch` |
| `M_CONNECTED_REF` | connected launch environment | absolute owner-private signed reference file | none; required | `connected_host_references_required`; `connected_private_reference_invalid`; `connected_plan_or_reference_drift` after a change |
| `M_AUTH_PUBKEY_FILE` | connected launch environment | absolute owner-private public-only P-256 key file | none; required | `connected_host_references_required`; a launch scope naming another key hash is `exact_expiring_connected_scope_required` |
| `SSL_CERT_FILE` | connected launch environment | absolute owner-private trust certificate, pinned by hash | unset | `connected_private_reference_invalid` |
| `TYPESAFE_API_KEY` | supervisor process environment at `template connected-launch` | present and non-empty; the value is never written to a plan or log | unset | `connected_credential_unavailable` before any launch attempt |
| `M_EFFECT_DIRECTORY` | connected launch environment | owner-private directory with existing private `claim-one` and `claim-two` subdirectories | none; required | `connected_host_references_required` |
| `M_TASKS` | connected launch environment | `two`, `duplicate` | `two` | `connected_host_references_required`; `duplicate` is refused with `duplicate_task_identity` and no effect |
| `M_HOLD` | connected launch environment | `0`, `1` | `0` | `connected_host_references_required`, also when `1` without `M_RELEASE_PATH` |
| `M_RELEASE_PATH` | connected launch environment | absolute path the operator creates to release a hold | unset | required when `M_HOLD` is `1` |
| `M_APPROVAL` | connected launch environment | `0`, `1` | unset: the fixture host approves | `connected_host_references_required`; `0` denies approval and writes no claim effect |

## Unsupported cases

Each item is refused or left pending by the code and tests named in this
reference; none is silently adapted.

- A console caller that is not a bounded explicit request loop: binding refuses with `bounded explicit request loop`.
- A fabricated or partly valid citation, or an unsupported critical claim: `critical claim unsupported or citation invalid`, with no support, audit or release file.
- Denied host approval or a request outside the reviewed shape: `claim host permission or shape refused`.
- A generated critical claim that differs from the host request: `generated critical claim differs from host request`. A revision that removes every claim: `empty claim revision refused`.
- Raw support or audit bytes that do not read back exactly: `claim raw effect readback failed`.
- A repeated task ID: `duplicate_task_identity`. More tasks than the reviewed limit: `claim task budget refused`.
- More than one successful task ID in the off-mode fixture, a real permit register, production audit and source-truth adjudication: outside this fixture.
- A requested mode other than shadow at `template connected-plan`: `connected_mode_requires_observed_gate`. Canary and active need separate observed gates.
- A launch environment name or value outside the table above, or a missing required reference: `connected_host_references_required`.
- An installed binding from another host profile: `connected_host_profile_binding_mismatch`.
- A changed reference, source or plan after planning: `connected_plan_or_reference_drift`; a second launch of one session: `connected_launch_already_attempted`.
- Any platform other than Linux x86-64 CPython 3.13 for the installed stages, a missing offline wheelhouse, connected upgrade for this row, provider operation, canary or active mode and measured benefit: not qualified here and recorded as pending.
