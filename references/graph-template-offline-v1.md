# L graph identity offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification of the narrow
`python.L@1.0` tail-call host in mode `off`. The source contract pins the
unchanged [graph oracle](../examples/graph-system/entities.py) and the
[host graph consumer](../examples/use-case-host/graph_runtime.py) by exact
bytes. `inspect_use_case_source(root, "L")` reads both without importing
target modules. It cannot bind an arbitrary graph database.
This fixture tests identity reconciliation of two already supplied entities;
it neither extracts a graph from source material nor retrieves answers from it.

Run the focused offline journey with a previously prepared private wheelhouse:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_graph_host.py \
    tests/test_use_case_graph_installed.py \
    tests/test_use_case_graph_bind.py \
    tests/test_use_case_graph_bound_installed.py
```

The test builder creates a separate reviewed regular `graph_host` package
with one L tail-call seam. It copies the graph oracle unchanged and the
byte-pinned consumer, then rescans the host. The old host's deterministic
baseline action and the generated alternative both use the same code-owned
graph consumer; the generated adapter is not hand-edited. It validates and
materializes the template, plans the exact source edit, runs isolated baseline
verification, applies, and checks the modified receipt. The #55 package and
install plans bind the applied tree, external modified receipt digest,
template, offline wheels, build tools and off-mode configuration. A #56
session with an externally retained install receipt and exact expiring scope
normally launches the installed `graph-host` console.

The consumer accepts only the finite `reconcile_same` request with a task ID.
Host-owned approval, current revision, separately retained expected revision,
two exact entity snapshots and pre-mutation audit are required. It calls the
unchanged `reconcile` oracle. The installed fixture supplies `GRAPH_DB_PATH`
for an external SQLite file under an owner-private `0700` directory. A
`BEGIN IMMEDIATE` transaction checks the stored entities, provenance and
revision, inserts the audit before the merge record, advances the revision
with a compare-and-swap, and commits both records together with SQLite full
synchronous mode. A separate read-only connection checks committed entities,
revision, and the full ordered audit/merge receipt history before an effect is
reported. A historical receipt changed without changing row count is refused.
The fixture accepts at most 32 committed reconciliation records; a 33rd is
refused before mutation.
Stale revision,
conflicting entity, missing approval, changed action or failed audit creates
no new merge or release file. Tests independently query the database and
compare it with the installed console's raw effect; the database itself is
the durable fixture effect, rather than a JSON assertion about in-memory
state. `GRAPH_EFFECT_PATH` and `GRAPH_READY_PATH` remain separate external
files; the JSON effect is exclusive, mode `0600`, and fsynced.

The test disables the first generation, builds and installs a separately
reviewed 1.0.1 fixture version, stages and launches it under a new exact
scope, reads its graph effect, disables it and rolls the session back to the
retained 1.0.0 generation. Both owned source edits are restored. The two
versions have identical finite graph semantics. Generation rollback does
not reverse either graph effect.

The separate source-bound journey uses `prepare_template_binding` on a fresh
inventory of the reviewed L task-loop console, then materializes, plans,
verifies, applies, and checks the owned source edit before packaging. Its
installed normal command runs under an exact off-mode session scope. An
independent SQLite readback checks the committed reconciliation and provenance;
a second installed command against the same revision refuses the conflict
without another effect. The journey then disables, installs a reviewed 1.0.1
version, upgrades, observes, disables, rolls the session back to the retained
1.0.0 generation, and restores both owned source edits. This is an offline
synthetic installed fixture, with no provider call or measured benefit.

This SQLite transaction records reconciliation of one fixed pair; it
does not collapse the two entity rows into a canonical node or reject a repeat
of the same pair under a later approved revision. It does not synthesize a
graph from documents, authorize semantic identity, or measure graph quality.
The classifier always proposes `same` for those two fixed entities. Database
file creation, merge-record commit and JSON effect creation are
not one transaction: an interrupted post-commit JSON write requires manual
reconciliation, never blind retry. The test does not establish concurrency
across independent hosts, arbitrary entity identity, connected/provider
authority, or production approval. Generation rollback retains both database
effects; it does not reverse a reconciliation record.

## Quickstart

Ordered commands for a separately reviewed L host with the documented caller
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
jev-integration-evaluator template validate --repo /private/graph-host --request /private/l-request.json

# 2. Bind the reviewed console caller, then materialize planner inputs.
jev-integration-evaluator template bind --repo /private/graph-host --request /private/l-request.json --binding /private/l-binding.json --out /private/l-bound
jev-integration-evaluator template materialize --repo /private/graph-host --request /private/l-bound/template-request.json --out /private/l-render

# 3. Plan, record the baseline, apply the exact bundle and verify it.
jev-integration-evaluator implement-plan --repo /private/graph-host --inventory /private/l-render/reviewed-inventory.json --candidate CANDIDATE_ID --spec /private/l-render/implementation-spec.json --out /private/l-bundle
jev-integration-evaluator implement-verify --phase baseline --repo /private/graph-host --bundle /private/l-bundle --approve-execution
jev-integration-evaluator implement-apply --repo /private/graph-host --bundle /private/l-bundle --approve BUNDLE_DIGEST --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /private/graph-host --bundle /private/l-bundle --approve-execution --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo /private/graph-host --bundle /private/l-bundle --trusted-receipt-sha256 MODIFIED_RECEIPT_SHA256

# 4. Configure and install offline. The package request carries the reviewed
#    off-mode configuration and its independently retained digest.
jev-integration-evaluator template package --request /private/l-package-request.json --out /private/l-package-plan.json
jev-integration-evaluator template package-build --plan /private/l-package-plan.json --approve-plan-sha256 PACKAGE_PLAN_SHA256
jev-integration-evaluator template install-plan --package-plan /private/l-package-plan.json --package-receipt /private/l-package-receipt.json --out /private/l-install-plan.json
jev-integration-evaluator template install --plan /private/l-install-plan.json --approve-plan-sha256 INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/l-install-plan.json

# 5. Normal start of the installed `graph-host` console in mode off, then
#    independent observation and status.
jev-integration-evaluator template delivery-plan --install-plan /private/l-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --observation /private/l-observation.json --launch-environment /private/l-launch-environment.json --out /private/l-delivery-plan.json
jev-integration-evaluator template deploy --session /private/l-session --plan /private/l-delivery-plan.json
jev-integration-evaluator template deploy --session /private/l-session --scope /private/l-launch-scope.json --approve-scope-sha256 LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/l-session --trusted-session-head SESSION_HEAD_SHA256
jev-integration-evaluator template status --session /private/l-session --trusted-session-head SESSION_HEAD_SHA256

# 6. Disable, upgrade to a separately reviewed and installed generation,
#    roll the generation back, then restore the owned source edit.
jev-integration-evaluator template disable --session /private/l-session --scope /private/l-disable-scope.json --approve-scope-sha256 DISABLE_SCOPE_SHA256
jev-integration-evaluator template upgrade --session /private/l-session --plan /private/l-delivery-plan-v2.json --scope /private/l-upgrade-scope.json --approve-scope-sha256 UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/l-session --scope /private/l-rollback-scope.json --approve-scope-sha256 ROLLBACK_SCOPE_SHA256
jev-integration-evaluator implement-rollback --repo /private/graph-host --bundle /private/l-bundle --approve ROLLBACK_DIGEST
```

The upgrade plan in step 6 is a second `template delivery-plan` result for a
second reviewed host version that went through steps 1 to 4 on its own. A
launch after `template upgrade` and the later `template disable` each need a
new exact scope.

Optional offline synthetic connected shadow, with the finite `graph-l-v1`
profile and a host that includes the reviewed `connected_authority.py` loader
before its final scan and binding:

```bash
jev-integration-evaluator template connected-installed-bind --package-plan /private/l-package-plan.json --package-receipt /private/l-package-receipt.json --install-plan /private/l-install-plan.json --install-receipt /private/l-install-receipt.json --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --out /private/l-installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/l-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --installed-binding /private/l-installed-binding.json --trusted-binding-sha256 BINDING_SHA256 --observation /private/l-connected-observation.json --launch-environment /private/l-connected-environment.json --host-profile graph-l-v1 --out /private/l-connected-plan.json
jev-integration-evaluator template connected-configure --session /private/l-connected-session --plan /private/l-connected-plan.json --approve-plan-sha256 CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/l-connected-session --scope /private/l-connected-launch-scope.json --approve-scope-sha256 CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/l-connected-session
jev-integration-evaluator template connected-stop --session /private/l-connected-session --scope /private/l-connected-stop-scope.json --approve-scope-sha256 CONNECTED_STOP_SCOPE_SHA256
```

Connected shadow only observes: the host keeps its deterministic baseline
effect. See the [connected reference](graph-template-connected-v1.md) for the signed
references and the fault schedule. No command here contacts a provider,
enables canary or active mode, or measures benefit.

## Parameters and bindings

A launch environment is a JSON object of string values passed with
`--launch-environment`. `template connected-plan` accepts only the names
listed here for the `graph-l-v1` profile; any other name, including the
supervisor-injected `L_CONNECTED_REF_SHA256` and `L_AUTH_PUBKEY_SHA256`,
is refused with `connected_host_references_required`. These finite controls
select reviewed host schedules; none grants runtime, egress or activation
authority.

| Name | Where | Allowed values | Default | What refuses |
| --- | --- | --- | --- | --- |
| `template_id`, `template_version`, `backend`, `profile` | template request | `python.bounded-tail-call`, `1.0.0`, `python`, `module-tail-call-v1` | none; required | `template validate` rejects any other value or changed source |
| `version` | binding input | `1.0` | none; required | `template bind` rejects the binding |
| `script` | binding input | `graph-host`, a console script declared in `pyproject.toml` | none; required | `Declared console script is absent or ambiguous` |
| `startup_inputs` | binding input | `budget_limits`, `audit_log`, `dependency_plan` and `startup_options`, each naming a zero-argument factory in the console module (`limits`, `audit`, `dependencies`, `options` in the fixture) | none; all four required | `template bind` rejects a missing or drifted factory |
| `configuration`, `reviewed_configuration_sha256` | package request | strict off-mode `{"jev_runtime": {"mode": "off", "credential_ref": null}}` and its digest | none; required | `reviewed_configuration_drift` at package planning; `installed_configuration_drift` at status |
| `console_script` | package request | `graph-host` | none; required | package planning rejects a script the host does not declare |
| `JEV_TEMPLATE_WHEELHOUSE` | test input | absolute private wheelhouse directory | unset | unset: the installed test modules skip, which is not evidence |
| `GRAPH_DB_PATH` | off-mode and connected launch environment | absolute SQLite path under an owner-private `0700` directory | unset: in-memory fixture graph | a linked, relative or non-private path; `graph database identity or revision conflict` |
| `GRAPH_EFFECT_PATH` | off-mode and connected launch environment | fresh absolute effect file under an owner-private directory | none; required | `GRAPH_EFFECT_PATH is required`; an existing path is refused as not fresh |
| `GRAPH_READY_PATH` | off-mode and connected launch environment | fresh absolute ready marker | unset: no marker | an existing marker stops the fixture host |
| `--host-profile` | `template connected-plan` | `graph-l-v1` | omitted selects the legacy Alpha profile | `connected_host_profile_binding_mismatch` |
| `L_CONNECTED_REF` | connected launch environment | absolute owner-private signed reference file | none; required | `connected_host_references_required`; `connected_private_reference_invalid`; `connected_plan_or_reference_drift` after a change |
| `L_AUTH_PUBKEY_FILE` | connected launch environment | absolute owner-private public-only P-256 key file | none; required | `connected_host_references_required`; a launch scope naming another key hash is `exact_expiring_connected_scope_required` |
| `SSL_CERT_FILE` | connected launch environment | absolute owner-private trust certificate, pinned by hash | unset | `connected_private_reference_invalid` |
| `TYPESAFE_API_KEY` | supervisor process environment at `template connected-launch` | present and non-empty; the value is never written to a plan or log | unset | `connected_credential_unavailable` before any launch attempt |
| `GRAPH_SECOND_EFFECT_PATH` | connected launch environment | fresh absolute effect file for the second task | none; the two-task fixture host requires it | `connected_host_references_required` for an unlisted name |
| `L_TASKS` | connected launch environment | `two`, `duplicate` | `two` | `connected_host_references_required`; `duplicate` is refused by the generated loop before any effect |
| `L_HOLD` | connected launch environment | `0`, `1` | `0` | `connected_host_references_required` |
| `L_RELEASE_PATH` | connected launch environment | absolute path the operator creates to release a hold | unset | with `L_HOLD` `1` the held fixture host stops after 15 seconds without it |
| `L_APPROVAL` | connected launch environment | `0`, `1` | unset: the fixture host approves | `connected_host_references_required`; `0` denies approval and no merge is committed |
| `L_EXPECTED_REVISION` | connected launch environment | `0`, `1` | `0` | `connected_host_references_required`; `1` against a fresh database is a revision conflict with no effect |

## Unsupported cases

Each item is refused or left pending by the code and tests named in this
reference; none is silently adapted.

- A console caller that is not a bounded explicit request loop, including the single-return form: binding refuses with `bounded explicit request loop`.
- Any graph action other than the finite `reconcile_same` request with a task ID: `finite graph action and task ID required`.
- A stale expected revision or a different stored entity: `graph database identity or revision conflict`. Missing approval or a failed audit commits nothing: `graph merge did not satisfy host postconditions`.
- A changed historical receipt: `graph database history conflict`. A 33rd reconciliation record: `graph database revision limit reached`.
- A repeated task ID in one schedule: `duplicate_task_identity`, before startup.
- Graph extraction from source material, entity canonicalization, refusing a later approved repeat of the same pair, and arbitrary graph databases: outside this fixture.
- A requested mode other than shadow at `template connected-plan`: `connected_mode_requires_observed_gate`. Canary and active need separate observed gates.
- A launch environment name or value outside the table above, or a missing required reference: `connected_host_references_required`.
- An installed binding from another host profile: `connected_host_profile_binding_mismatch`.
- A changed reference, source or plan after planning: `connected_plan_or_reference_drift`; a second launch of one session: `connected_launch_already_attempted`.
- Any platform other than Linux x86-64 CPython 3.13 for the installed stages, a missing offline wheelhouse, connected upgrade for this row, provider operation, canary or active mode and measured benefit: not qualified here and recorded as pending.
