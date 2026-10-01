# Registered-tool template quickstart v1

This is the single operator document for the Python recipe C registered-tool
template (`python.bounded-tail-call@1.0.0`, recipe `python.C@1.0`) on the
declared **Linux x86-64, CPython 3.13, single-process package/console**
profile. It orders the existing commands into one journey, states what each
step needs, writes and returns, and shows which gates are qualified, which are
only implemented and which are pending.

Every qualified row below is **offline synthetic fixture evidence**. Nothing in
this document establishes provider operation, canary or active eligibility, or
measured benefit; see [What this does not establish](#what-this-does-not-establish).
The deeper contracts stay authoritative:
[template catalog](template-catalog-v1.md),
[console entrypoint binding](template-python-entrypoint-v1.md),
[executable integrations](executable-integrations.md),
[package and installation](template-installation-v1.md),
[delivery session](template-delivery-session-v1.md),
[installed binding](connected-installed-binding-v1.md),
[connected shadow delivery](connected-delivery-v1.md),
[stopped generation transfer](connected-generation-transfer-v1.md) and the
[independent Alpha host](../tests/independent_hosts/registered_alpha/README.md).

All paths and upper-case digests in the commands are placeholders. Use real
owner-private absolute paths outside the host and digests you retained
yourself. Do not put keys, raw prompts, private source or credential-bearing
URLs into requests, scopes, plans, reports or logs. A command sequence is not
an approval shortcut: every `--approve-*` and `--trusted-*` value must come from
a channel that is independent of the file it approves.

The flags below were taken from the argument parser in
`jev_integration_evaluator/cli.py`; `tests/test_registered_tool_quickstart.py`
fails if a subcommand or flag shown here is not accepted by that parser. The
qualification suites drive most lifecycle stages through the equivalent Python
API rather than through the console command.

## Platform and tool pins

| Pin | Value | Where it is enforced |
|---|---|---|
| Operating system and machine | Linux, `x86_64` (the installer also accepts the `amd64` spelling) | `template_installation` refuses with `linux_x86_64_cpython313_required`; `template_delivery` with `delivery_profile_requires_linux_x86_64_cpython_3_13` |
| Interpreter | CPython 3.13; the package plan binds the exact binary SHA-256, patch version, SOABI and platform | package plan `profile`; `interpreter_must_match_planner` |
| Evaluator | `jev-integration-evaluator` `1.3.0.dev12` | template manifest and lock; the Alpha fixture depends on `jev-integration-evaluator==1.3.0.dev12` |
| Template, recipe, renderer | `python.bounded-tail-call@1.0.0`, recipe version `1.0`, `template-renderer-v1`, grammar `module-tail-call-v1` | `template inspect`; `template-lock-v1` |
| Runtime model | `jev-1.13.0` | template manifest; connected options reference |
| Build backend | setuptools PEP 517 with `setuptools` and `wheel` pinned in `build-system.requires` (the Alpha fixture pins `setuptools==84.0.0`, `wheel==0.48.0`) | `unpinned_build_backend`, `build_tool_pins_missing`, `build_tool_version_drift` |
| `pip` | the exact installed version named in the package request `build_tools`; no index access | `build_tool_version_drift`; installs use `--require-hashes --no-index` |
| Wheelhouse | explicit offline directory with a SHA-256 for every wheel and a fully resolved lock row for every dependency | `wheel_hash_drift`, `requirements_lock_invalid`, `wheel_abi_or_platform_unsupported` |
| Signature verifier (connected only) | `/usr/bin/openssl`, OpenSSL 3, P-256 public key with SHA-256 detached signatures | the reviewed host options loader and `template_connected_generation` |
| Process model | one console process started from a `[project.scripts]` entry; one controller per session | owner lock: `delivery_session_owned_by_another_controller` |

The console binder itself reads source on Python 3.10 or newer; the installed
profile above is narrower. The hosted matrix result for any other interpreter
or platform is not implied by this table.

## Run identity

- `template journey-create` assigns one UUID `run_id` and returns
  `journey_head_sha256`. Every later `journey-record`, `journey-status` and
  `journey-promote` must present the **current** head through
  `--trusted-journey-head`; retain each new head outside the session.
- `template journey-promote` creates the off-mode runtime session under
  `<journey>/runtime` with the **same** `run_id`. `template deploy --plan`
  without a journey instead assigns a fresh `run_id`.
- A delivery session returns `run_id`, `plan_sha256` and `session_head_sha256`.
  Each scope (`template-delivery-scope-v1`) names that run, that plan and the
  current head in `trusted_session_head`, an expiry, `revoked` and one grant
  per operation. Every effect appends to the hash-chain journal and changes
  the head, so a scope is usable once.
- `template upgrade` keeps the `run_id` and selects a new plan; `rollback`
  keeps it and restores the previous plan. The Alpha upgrade fixture checks the
  retained old generation's final effect under a separate, new run.
- `template connected-configure` creates a **separate** connected session with
  its own `run_id`. Its scope (`connected-delivery-scope-v1`) binds `run_id`,
  `plan_sha256`, `public_key_sha256`, `trusted_session_head`, one `action`
  (`launch` or `stop`) and `expires_at`.
- A stopped generation transfer creates a child session with the parent's
  `run_id`, one durable ledger and the original cutoff.
- A digest printed by a command identifies bytes. It becomes an approval only
  when you compared it with a value retained independently.

## Journey

### 1. Inspect, bind and materialize

Inputs: the current reviewed host, a `template-request-v1` request holding the
current reviewed inventory and implementation specification, and a
`template-entrypoint-binding-v1` file naming the console script and the
existing host-owned startup factories. The binder runs before materialization
because it derives the entrypoint edit that the materialized request carries.

```bash
jev-integration-evaluator template list --json
jev-integration-evaluator template inspect python.bounded-tail-call --version 1.0.0
jev-integration-evaluator template bind --repo /reviewed/host \
  --request /private/request.json --binding /private/console-binding.json \
  --out /private/new-binding
jev-integration-evaluator template validate --repo /reviewed/host \
  --request /private/new-binding/template-request.json
jev-integration-evaluator template materialize --repo /reviewed/host \
  --request /private/new-binding/template-request.json --out /private/new-render
```

| Step | Writes | Expected status | Retain |
|---|---|---|---|
| `template bind` | `template-request.json`, `binding-report.json`, `bind-status.json` in a new directory | `bound` (binding report `planned_not_applied`) | `request_sha256` |
| `template validate` | nothing | `validated` | none |
| `template materialize` | `template-manifest.json`, `template-request.json`, `implementation-spec.json`, `reviewed-inventory.json`, `template-lock.json`, `render-status.json` | lock `materialized`; marker `complete` | `lock_sha256` |

Refusals arrive on stderr as `{"schema_version": "1.0", "status": "rejected"}`
with exit 2: stale source, inventory or review mismatch, unsupported source or
caller shape, an occupied adapter path, output inside the host, a symlink
path, or an existing output directory (`Template output collision`). None of
these commands changes, installs or executes the host.

### 2. Plan, baseline, reviewed apply and modified verification

```bash
jev-integration-evaluator implement-plan --repo /reviewed/host \
  --inventory /private/new-render/reviewed-inventory.json \
  --candidate REVIEWED_CANDIDATE \
  --spec /private/new-render/implementation-spec.json --out /private/new-bundle
jev-integration-evaluator template journey-create --session /private/journey \
  --source-root /reviewed/host --bundle /private/new-bundle --source-kind single
jev-integration-evaluator implement-verify --phase baseline --repo /reviewed/host \
  --bundle /private/new-bundle --approve-execution --out /private/anchors/baseline-receipt.json
jev-integration-evaluator template journey-record --session /private/journey \
  --trusted-journey-head LAST_RETAINED_JOURNEY_HEAD --stage baseline_anchored \
  --trusted-receipt-sha256 RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-apply --repo /reviewed/host \
  --bundle /private/new-bundle --approve REVIEWED_BUNDLE_DIGEST \
  --baseline-sha256 RETAINED_BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /reviewed/host \
  --bundle /private/new-bundle --approve-execution \
  --baseline-sha256 RETAINED_BASELINE_RECEIPT_SHA256 --out /private/anchors/modified-receipt.json
jev-integration-evaluator implement-status --repo /reviewed/host \
  --bundle /private/new-bundle --trusted-receipt-sha256 RETAINED_MODIFIED_RECEIPT_SHA256
jev-integration-evaluator template journey-record --session /private/journey \
  --trusted-journey-head LAST_RETAINED_JOURNEY_HEAD --stage source_verified \
  --trusted-receipt-sha256 RETAINED_MODIFIED_RECEIPT_SHA256
```

| Step | Writes | Expected status | Retain and approve |
|---|---|---|---|
| `implement-plan` | private bundle outside the host (plan, diff, manifest, preimages, schedule) | `planned` | review the bundle and diff; `bundle_digest` is the later `--approve` value |
| `template journey-create` | journey state `template-delivery-journey-v1`; result `template-delivery-journey-result-v1` | stage `source_planned` | `run_id`, `journey_head_sha256` |
| `implement-verify --phase baseline` | `baseline-receipt.json` in the bundle (`implementation-receipt` schema) | `baseline_passed` | `receipt_sha256`, retained outside the bundle |
| `implement-apply` | owned host edits plus recovery journal | `applied_unverified` | approves the exact bundle digest and baseline digest |
| `implement-verify --phase modified` | `verification-receipt.json` in the bundle | `verified` | `receipt_sha256`, retained outside the bundle |
| `implement-status` | nothing; never executes the host | `verified` with `receipt_trust` `externally_anchored_execution` | `rollback_digest` |

`implement-verify` executes scheduled host checks and needs separate execution
authority: without `--approve-execution` it refuses with `Missing scope: target
execution; planning and status never run host code`, and it exits 3 on
`verification_failed`. Apply refuses with `Exact reviewed bundle digest approval
is required`, `An externally retained baseline receipt digest is required`,
`Baseline verification did not pass`, `Owned path drift before apply`, or
`Bundle needs explicit recovery/rollback, not another application`. Status exits
3 for `blocked_recovery` or `verification_failed`. A receipt copied from the
bundle is not an external anchor. `implement-rollback --repo ... --bundle ...
--approve ROLLBACK_DIGEST` restores only matching owned bytes.

### 3. Package plan and build, install plan and install

Inputs: a private `template-package-request-v1` request naming the applied host,
the bundle and its externally retained modified receipt digest, the
materialized template directory, the reviewed package-source and configuration
digests, the exact interpreter and build tools, the offline wheelhouse and
lock rows, new owner-private output directories, the console script and
`env:NAME` secret references only.

```bash
jev-integration-evaluator template package --request /private/package-request.json \
  --out /private/package-plan.json
jev-integration-evaluator template package-build --plan /private/package-plan.json \
  --approve-plan-sha256 REVIEWED_PACKAGE_PLAN_SHA256
jev-integration-evaluator template package-status --plan /private/package-plan.json
jev-integration-evaluator template install-plan --package-plan /private/package-plan.json \
  --package-receipt /private/package/package-receipt.json --out /private/install-plan.json
jev-integration-evaluator template install --plan /private/install-plan.json \
  --approve-plan-sha256 REVIEWED_INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/install-plan.json
```

| Step | Writes (`kind`) | Expected status | Retain and approve |
|---|---|---|---|
| `template package` | package plan (`template-package-plan-v1`) | `planned` | review, then approve `plan_sha256` |
| `template package-build` | one pure-Python wheel and `package-receipt.json` (`template-package-receipt-v1`) | `built` | `receipt_sha256` |
| `template package-status` | nothing | `built_recorded` | none |
| `template install-plan` | install plan (`template-install-plan-v1`) | `planned` | review, then approve `plan_sha256` |
| `template install` | owned private environment and `install-receipt.json` (`template-install-receipt-v1`), off-mode configuration | `installed` | `receipt_sha256` |
| `template install-status` | nothing | `installed_recorded` | `generation_sha256` when recovery is needed |

Record each stage on the same run with `template journey-record --session ...
--trusted-journey-head ... --stage STAGE`: `package_planned` and
`install_planned` take `--plan`; `package_built` takes `--receipt` and
`--trusted-receipt-sha256`; `installed` takes `--trusted-receipt-sha256`.

Documented refusals include `exact_build_authority_required`,
`exact_install_authority_required`, `applied_source_unverified`,
`template_or_applied_source_verification_failed`, `reviewed_package_source_drift`,
`reviewed_configuration_drift`, `inline_credential_unsupported`,
`secret_reference_invalid`, `connected_mode_requires_separate_validation`,
`native_wheel_unsupported`, `wheel_hash_drift`,
`package_output_collision_or_overlap`, `build_interrupted_review_required` and
`install_interrupted_recovery_required`. Other status values are `absent`,
`interrupted_recovery_required`, `ownership_or_artifact_drift` and
`installed_drift`. An interrupted generation is adopted or removed only through
`template package-recover` or `template install-recover` with
`--approve-plan-sha256` and, for removal, `--approve-generation-sha256`; a build
or install is never blindly repeated. The runtime stays off, and an install
receipt is not a launch, reachability or authority claim.

### 4. Delivery session: configure, launch, status, stop, disable

Inputs: the install plan, the externally retained install receipt digest and a
`template-delivery-observation-v1` file whose `ready`, `entrypoint_reached` and
`integration_reachable` checks come from an independent host contract. The
ready and integration checks must use different external files.

```bash
jev-integration-evaluator template delivery-plan --install-plan /private/install-plan.json \
  --trusted-install-receipt-sha256 RETAINED_INSTALL_RECEIPT_SHA256 \
  --observation /private/observation.json --out /private/delivery-plan.json
jev-integration-evaluator template deploy --session /private/delivery-session \
  --plan /private/delivery-plan.json
jev-integration-evaluator template deploy --session /private/delivery-session \
  --scope /private/launch-scope.json --approve-scope-sha256 APPROVED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/delivery-session \
  --trusted-session-head LAST_RETAINED_SESSION_HEAD
jev-integration-evaluator template status --session /private/delivery-session \
  --trusted-session-head LAST_RETAINED_SESSION_HEAD
jev-integration-evaluator template stop --session /private/delivery-session \
  --scope /private/stop-scope.json --approve-scope-sha256 APPROVED_STOP_SCOPE_SHA256
jev-integration-evaluator template disable --session /private/delivery-session \
  --scope /private/disable-scope.json --approve-scope-sha256 APPROVED_DISABLE_SCOPE_SHA256
```

On a journey, `template journey-promote --session /private/journey
--trusted-journey-head ... --observation ...` replaces the `deploy --plan` call
and keeps the journey `run_id`. `template resume --session ...
--trusted-session-head ...` reconciles a pending intent without replaying a
possibly executed invocation.

| Step | Writes (`kind`) | Expected `stage` and `next_action` | Retain and approve |
|---|---|---|---|
| `template delivery-plan` | delivery plan (`template-delivery-plan-v1`) | plan only | `plan_sha256` |
| `template deploy --plan` (configure) | owner-private session (`template-delivery-session-v1`), `events.jsonl`, plan archive; returns `template-delivery-result-v1` | `installed`, `supply_exact_launch_scope` | `run_id`, `session_head_sha256` |
| `template deploy --scope` (launch) | `launch_pending` and `launched` journal rows | `launched`, `observe_independent_host_postconditions` | approves `scope_sha256` with the `launch` grant; retain the new head |
| `template observe` | `observed` row with separate recorded observations | `disable_or_review_outcome` | new head |
| `template status` | nothing | current stage; `current_process_alive`, `current_ready`, `current_integration_reachable` rechecked | none |
| `template stop` | `stop_pending`, `stopped` rows | `stopped`, `review_outcomes_and_owned_rollback` | scope with the `stop` grant |
| `template disable` | `stop_pending`, `disabled` rows | `disabled`; a later launch scope is refused | scope with the `disable` grant |

Every result keeps `provider_qualification` at `not_run`, `observed_benefit` at
`false` and `provider_reachable` false; the supervisor forces
`JEV_RUNTIME_MODE=off`. Documented refusals include
`template_deploy_requires_exactly_plan_or_scope`,
`exact_delivery_scope_digest_required`, `exact_delivery_scope_and_head_required`
(wrong run, plan, head or grant, or a revoked scope), `delivery_scope_expired`,
`externally_retained_install_receipt_required`,
`installed_generation_drift_or_unverified`,
`readiness_and_integration_require_independent_checks`,
`delivery_observation_baseline_drift`,
`delivery_launch_environment_invalid_or_sensitive`,
`delivery_launch_already_attempted_or_blocked`,
`delivery_process_already_running`, `externally_retained_session_head_required`
and `delivery_stop_requires_known_process`. If `resume` reports unknown launch
effects (`review_unknown_launch_effects`), inspect the host effect sink outside
the session before any new invocation.

### 5. Upgrade and rollback

Prepare the new version as a fresh source-bound journey through sections 1 to 3,
then write a new delivery plan for its install plan.

```bash
jev-integration-evaluator template upgrade --session /private/delivery-session \
  --plan /private/new-delivery-plan.json --scope /private/upgrade-scope.json \
  --approve-scope-sha256 APPROVED_UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/delivery-session \
  --scope /private/rollback-scope.json --approve-scope-sha256 APPROVED_ROLLBACK_SCOPE_SHA256
```

| Step | Requires | Expected `stage` and `next_action` |
|---|---|---|
| `template upgrade` | a stopped old generation; scope with the `upgrade` grant and `upgrade_plan_sha256` equal to the new plan | `upgrade_staged`, `supply_fresh_off_mode_launch_scope`; nothing is launched |
| `template rollback` after an upgrade | scope with the `rollback` grant and `rollback_digest` equal to the returned `previous_generation_rollback_digest` | `rolled_back`, `supply_fresh_off_mode_launch_scope`; the retained old generation is selected, not launched |
| `template rollback` on the first generation | scope `rollback_digest` equal to the owned source `rollback_digest` from `implement-status` | `rolled_back`, `retain_owned_generation_for_review`; owned source bytes restored, installed environment retained |

Documented refusals: `upgrade_requires_completed_old_generation_stop`,
`upgrade_old_process_still_alive`, `exact_upgrade_plan_authority_required`,
`incompatible_delivery_schema_requires_migration`,
`upgrade_requires_new_disjoint_owned_generation`,
`delivery_rollback_requires_stopped_session`,
`exact_previous_generation_rollback_required`,
`exact_verified_owned_rollback_required` (including a concurrent source edit)
and `owned_source_rollback_incomplete`. There is no automatic launch and no
exposure expansion on either step.

### 6. Connected shadow on the installed generation

This path is opt-in and separate. Package and install stay off. Shadow is the
only mode `template connected-plan` accepts; a canary or active request is
refused with `connected_mode_requires_observed_gate`. Omit `--host-profile` for
the registered Alpha profile. The host owner provisions, outside the package
and the installed environment, an owner-private options reference and an issuer
**public** P-256 key; the launch environment file names both. The credential is
only a reference in plans; its value must be present in the launch environment
at `connected-launch` and nowhere else.

```bash
jev-integration-evaluator template connected-installed-bind \
  --package-plan /private/package-plan.json \
  --package-receipt /private/package/package-receipt.json \
  --install-plan /private/install-plan.json \
  --install-receipt /private/environments/GENERATION/install-receipt.json \
  --trusted-package-receipt-sha256 RETAINED_PACKAGE_RECEIPT_SHA256 \
  --trusted-install-receipt-sha256 RETAINED_INSTALL_RECEIPT_SHA256 \
  --out /private/installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/install-plan.json \
  --trusted-install-receipt-sha256 RETAINED_INSTALL_RECEIPT_SHA256 \
  --trusted-package-receipt-sha256 RETAINED_PACKAGE_RECEIPT_SHA256 \
  --installed-binding /private/installed-binding.json \
  --trusted-binding-sha256 RETAINED_BINDING_SHA256 \
  --observation /private/connected-observation.json \
  --launch-environment /private/connected-launch-environment.json \
  --out /private/connected-plan.json
jev-integration-evaluator template connected-configure --session /private/connected-session \
  --plan /private/connected-plan.json --approve-plan-sha256 REVIEWED_CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/connected-session \
  --scope /private/connected-launch-scope.json \
  --approve-scope-sha256 APPROVED_CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/connected-session \
  --trusted-session-head LAST_RETAINED_CONNECTED_HEAD
jev-integration-evaluator template connected-stop --session /private/connected-session \
  --scope /private/connected-stop-scope.json \
  --approve-scope-sha256 APPROVED_CONNECTED_STOP_SCOPE_SHA256
```

| Step | Writes (`kind`) | Expected result | Retain and approve |
|---|---|---|---|
| `template connected-installed-bind` | read-only binding report (`connected-installed-binding-v1`) | source, wheel `RECORD` and installed origins recomputed | `binding_sha256`, authenticated independently |
| `template connected-plan` | connected plan (`connected-delivery-plan-v1`), shadow only | plan only | review, then approve `plan_sha256` |
| `template connected-configure` | owner-private session (`connected-delivery-session-v1`); returns `connected-delivery-result-v1` | stage `installed`, `launch_attempts` 0 | `run_id`, `session_head_sha256` |
| `template connected-launch` | durable launch intent, then `launched` and `running` rows | stage `running`; one attempt only | scope with `action` `launch`, exact head, public-key hash and expiry |
| `template connected-status` | nothing | `evidence_type` `offline_protocol`, `requested_mode` `shadow`, `provider_reachable` null, `observed_benefit` null, `independent_checks`, `installed_sources_current`, `private_references_current` | none |
| `template connected-stop` | `stop_pending`, `stopped` rows | stage `stopped` | scope with `action` `stop` |

`template connected-resume --session ... --trusted-session-head ...` reconciles
a pending launch or stop without replay. Documented refusals:
`installed_receipt_or_generation_unverified`, `installed_wheel_record_mismatch`,
`installed_module_bytes_changed`, `installed_entrypoint_origin_changed`,
`installed_project_provenance_changed`, `connected_installed_binding_unverified`,
`connected_host_references_required`, `connected_private_reference_invalid`,
`connected_independent_outcome_schedule_required`,
`exact_connected_plan_approval_required`,
`exact_expiring_connected_scope_required`, `connected_credential_unavailable`,
`connected_launch_already_attempted`, `connected_observation_baseline_changed`,
`connected_plan_or_reference_drift`, `connected_reference_changed`,
`connected_original_cutoff_expired`, `connected_stop_requires_known_process` and
`externally_retained_connected_head_required`. The offline installed test checks
normal console startup and the exact stopped state with the host's hard gate
closed, and a shadow decision only with a separately permitted fixture.

### 7. Stopped connected generation transfer

Install and bind the second reviewed version through sections 1 to 3 and the
first two commands of section 6, with its own signed reference pointing at the
same ledger path and public key. The old session must be stopped and its
durable ledger must exist.

```bash
jev-integration-evaluator template connected-generation-plan \
  --old-session /private/connected-session --new-plan /private/new-connected-plan.json \
  --trusted-old-head RETAINED_STOPPED_OLD_HEAD \
  --old-dependencies /private/old-dependency-plan.json \
  --new-dependencies /private/new-dependency-plan.json \
  --limits /private/limits.json --action upgrade \
  --issued-at ISSUED_AT_UTC --expires-at EXPIRES_AT_UTC \
  --out /private/generation-grant.json
jev-integration-evaluator template connected-generation-transfer \
  --old-session /private/connected-session --new-session /private/new-connected-session \
  --trusted-old-head RETAINED_STOPPED_OLD_HEAD --grant /private/generation-grant.json \
  --signature-file /private/generation-grant.sig \
  --new-plan /private/new-connected-plan.json \
  --approve-new-plan-sha256 REVIEWED_NEW_CONNECTED_PLAN_SHA256 \
  --old-dependencies /private/old-dependency-plan.json \
  --new-dependencies /private/new-dependency-plan.json
jev-integration-evaluator template connected-generation-status \
  --old-session /private/connected-session --new-session /private/new-connected-session \
  --trusted-old-head RETAINED_STOPPED_OLD_HEAD --grant /private/generation-grant.json \
  --signature-file /private/generation-grant.sig
jev-integration-evaluator template connected-generation-reconcile \
  --old-session /private/connected-session --new-session /private/new-connected-session \
  --trusted-old-head RETAINED_STOPPED_OLD_HEAD --grant /private/generation-grant.json \
  --signature-file /private/generation-grant.sig
```

| Step | Writes (`kind`) | Expected result |
|---|---|---|
| `template connected-generation-plan` | **unsigned** grant (`connected-generation-transfer-v1`) outside the host | the private issuer signs `generation_transfer:<grant SHA-256>` elsewhere; only the detached signature and pinned public key reach the controller |
| `template connected-generation-transfer` | one ledger transfer transaction and an inert child session with the parent `run_id` | `ledger_receipt` plus child stage `generation_pending`; nothing is launched |
| `template connected-generation-status` | nothing (`connected-generation-status-v1`) | `ledger` status and `child_stage` |
| `template connected-generation-reconcile` | `generation_committed` row when the ledger shows `committed` | child stage `installed`; a later `connected-launch` still needs its own scope and credential |

A retained reverse transfer is the same sequence with `--action rollback` and a
fresh signed grant. Documented refusals:
`connected_generation_existing_ledger_required` (a missing ledger is never
recreated empty), `connected_generation_stopped_session_required`,
`connected_generation_exact_grant_required`,
`connected_generation_signature_invalid`,
`connected_generation_public_key_changed`, `connected_generation_plan_changed`,
`connected_generation_installed_binding_changed`,
`connected_generation_profile_not_supported`,
`connected_generation_stale_transfer` and `connected_generation_child_changed`.
The transfer never resets spend, extends the cutoff or changes the run ID.

## Support matrix

One row per declared gate. The list is defined once in
`jev_integration_evaluator/registered_tool_qualification.py`; the same list
drives the report in the next section, and a test fails if this table differs
from it. `qualified_offline_synthetic` means the cited modules exercise the gate
against local synthetic fixtures on the declared profile when their explicit
offline inputs are supplied; without those inputs the installed cases skip and
the gate is unrun in that run. `implemented_unqualified` means a driver and
tests exist but no qualification is claimed. `pending` means no offline test
can satisfy the gate.

| Gate | Covers | Status | Evidence modules |
|---|---|---|---|
| `template_materialize` | Catalog validation and materialized planner inputs | `qualified_offline_synthetic` | `tests/test_template_catalog.py` |
| `entrypoint_bind` | Console entrypoint binding and owned entrypoint edit | `qualified_offline_synthetic` | `tests/test_template_python_entrypoint.py` |
| `source_plan_verify_apply_rollback` | Source plan, baseline and modified verification, reviewed apply and owned rollback | `qualified_offline_synthetic` | `tests/test_executable_recipes.py`, `tests/test_package_lifecycle.py` |
| `package_install` | Offline package plan/build and install plan/install | `qualified_offline_synthetic` | `tests/test_template_installation.py` |
| `delivery_session_off` | Off-mode delivery session: configure, launch, status, observe, stop, disable, upgrade, rollback | `qualified_offline_synthetic` | `tests/test_template_delivery_session.py`, `tests/test_template_delivery_installed.py` |
| `independent_host_installed_journey` | Independent Alpha host installed journey with controlled faults | `qualified_offline_synthetic` | `tests/test_registered_alpha_oracle.py`, `tests/test_registered_alpha_installed_faults.py` |
| `installed_upgrade_rollback` | Independent Alpha host versioned upgrade and retained generation rollback | `qualified_offline_synthetic` | `tests/test_registered_alpha_installed_upgrade.py` |
| `second_independent_host` | Second independently authored work-queue host | `qualified_offline_synthetic` | `tests/test_work_queue_oracle.py`, `tests/test_work_queue_installed.py` |
| `composite_two_placements` | Two registered placements under one task and shared budget | `qualified_offline_synthetic` | `tests/test_registered_dual_composite.py` |
| `connected_shadow_local_protocol` | Installed binding and connected shadow against a local synthetic TLS protocol | `qualified_offline_synthetic` | `tests/test_connected_installed_binding.py`, `tests/test_connected_loader_public_keys.py` |
| `connected_generation_transfer` | Stopped connected generation transfer and signed reverse transfer | `implemented_unqualified` | `tests/test_connected_generation_controller.py`, `tests/test_connected_generation_ledger.py`, `tests/test_connected_generation_installed.py` |
| `provider_operation` | Authentic provider endpoint operation | `pending` | none; needs an authentic typed endpoint, a credential reference, and bounded host egress and spend scope |
| `authorized_canary` | Authorized canary with raw observed gate evidence | `pending` | none; needs raw observed canary holdouts and exact runtime and deployment receipts, with missing outcomes kept in the denominator |
| `authorized_active` | Authorized active with raw observed gate evidence | `pending` | none; needs raw observed active gate evidence and independently authenticated receipts |
| `measured_benefit` | Independently measured task benefit | `pending` | none; needs a frozen paired study with independent comparators (issue #48) |

### Unsupported or unqualified outside this matrix

| Path | State |
|---|---|
| Canary or active through `template connected-plan` | unsupported; refused with `connected_mode_requires_observed_gate` |
| Any platform other than Linux x86-64 CPython 3.13 for the commands in sections 3 to 7 | unsupported by this profile; native Windows has its own separate APIs and references |
| Poetry, uv, Conda, editable installs, containers, cloud installers, native host extensions | unsupported |
| Generic daemons, service registration, multiprocess workers, asynchronous entrypoints, namespace packages, dynamic plugins, decorators | unsupported by the binder and supervisor |
| Composite placement or cross-profile generation transfer | unsupported; no path in the transfer controller |
| A distributed budget across separately installed packages | not qualified; the dual fixture is one package and one process-local owner |
| Remaining fault schedules (provider timeout and malformed responses against an authentic endpoint, every crash point, power loss) | not qualified |

## Optional qualification report

`scripts/run_registered_tool_qualification.py` is an opt-in report step. It
runs no test, no target code and no network call. It reads one pytest JUnit XML
file that you produced separately and writes a
`registered-tool-qualification-report-v1` JSON file
([schema](../schemas/registered-tool-qualification-report-v1.schema.json)) to a
new path outside the checkout. Run pytest from the checkout root so module
names appear as `tests.test_*`.

```bash
python -m pytest -q --junitxml /private/reports/junit.xml
python scripts/run_registered_tool_qualification.py --junit /private/reports/junit.xml \
  --out /private/reports/registered-tool-qualification.json
python scripts/run_registered_tool_qualification.py --junit /private/reports/junit.xml \
  --out /private/reports/registered-tool-qualification-strict.json --require-offline-complete
```

Each gate status is computed only from the JUnit rows of its evidence modules:

| Report status | Meaning |
|---|---|
| `passed` | every evidence module has at least one case and every case ran and passed |
| `failed` | at least one case failed or errored |
| `unrun` | a module has no case in the file, or at least one case was skipped |
| `pending_authentic_evidence` | always, for `provider_operation`, `authorized_canary`, `authorized_active` and `measured_benefit`; a passing case with a matching name changes nothing |

The summary lists and counts the failed, unrun and pending gates; all gates,
including the pending ones, stay in `gate_count`, and `qualification_complete`
is always `false`. Exit 0 only means the report was written. With
`--require-offline-complete` the exit code is 3 unless every offline gate is
`passed`. Exit 2 means a refusal: `junit_report_unavailable_or_oversize`,
`junit_report_malformed`, `junit_report_declares_unsupported_markup`,
`report_must_be_outside_the_checkout`, `report_output_already_exists`,
`report_parent_directory_required` or `report_path_must_not_traverse_symlinks`.

Limits of the report: the JUnit file is caller supplied and unauthenticated; a
deselected case leaves no row, so compare the per-module case counts with the
retained run; JUnit does not identify the interpreter or platform, so record
them separately; `passed` for `connected_generation_transfer` reports that its
tests ran and passed and does not change its `implemented_unqualified` status.

## What this does not establish

- **Provider operation.** No command or test here contacts an authentic
  provider endpoint. Connected shadow evidence uses a loopback synthetic TLS
  protocol; `provider_reachable` is never recorded as true.
- **Canary or active eligibility.** There are no observed canary or active gate
  receipts. Both need raw observed holdouts recomputed by
  `HostRuntimeLifecycle`, exact runtime and deployment receipts, and existing
  host authority. No model and no report can grant that authority.
- **Measured benefit.** Release correctness does not assert task improvement.
  That requires the separate frozen paired study with independent comparators.
- **Authorization.** A plan, lock, receipt, binding digest, session head or
  qualification report is an identity. It is not an approval, an egress grant,
  a credential or permission to activate.
- **Other hosts and platforms.** The qualified hosts are independently authored
  disposable fixtures with local synthetic effects. They do not qualify a
  production application, another recipe, another language, native Windows or
  any interpreter that was not actually executed.
- **Connected upgrade and rollback.** The stopped generation transfer is
  implemented and tested offline but not claimed as qualified.
- **Complete fault coverage.** Controlled offline interruptions do not
  establish recovery from every crash point, power loss, or concurrent
  external revocation.
- **Current health.** Recorded observations are history. Only `status` and
  `connected-status` recheck the present state, as a bounded sample.
