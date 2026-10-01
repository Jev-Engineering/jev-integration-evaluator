# D retrieval offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification for the narrow
`python.D@1.0` tail-call profile in mode `off`. The source contract pins the
unchanged [RAG oracle](../examples/rag-system/pipeline.py), the separate
[retrieval consumer](../examples/use-case-host/retrieval_consumer.py), and the
finite [corpus](../examples/use-case-host/retrieval_corpus_v1.json) by exact
bytes. `inspect_use_case_source(root, "D")` reads those bytes without importing
the target. This does not bind an arbitrary RAG application.

Run the focused offline journey with a previously prepared private wheelhouse:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_retrieval_host.py \
    tests/test_use_case_retrieval_bind.py \
    tests/test_use_case_retrieval_bound_installed.py
```

The test builds a separate regular `retrieval_host` package with a reviewed
one-argument D tail-call seam. It validates and materializes the template,
plans the exact source edit, records baseline verification, applies the edit,
and verifies the modified host. The generated adapter is not hand-edited.
The #55 package/install plan binds the applied source tree, external modified
receipt digest, materialized template, pinned wheelhouse/build tools, and
off-mode configuration. The installed receipt identifies the owned console.
An externally retained install receipt digest and a distinct expiring scope
feed the #56 session for normal installed `retrieval-host` launch.

The host reads an already existing private `D_CORPUS_PATH` file, checks its
exact reviewed hash and revision 7, and requires host approval plus the
expected revision. The corpus carries stable passage, source, span, claim,
stance and provenance fields. The generated D selection must include the
supporting hit and the initially irrelevant contradictory and uncertain
passages for the same material claim. Missing, changed, stale, ambiguous or
unauthorized inputs refuse the write. The consumer calls the unchanged
`answer_with_evidence` oracle with its lexical baseline and a code-owned
finite answer consumer. The strict `retrieval-answer-handoff-v1` record retains
each selected passage's source, span, quote, claim, stance, exact corpus
provenance and initial relevance. The independent corpus contains supporting,
contradictory and uncertain status passages. Its normal installed command
emits `withheld_conflict` with a null answer while retaining all three,
including the two initially irrelevant passages. Missing material passages
or missing exact support emit `withheld_missing`; neither state releases text.
A separate pure contract test shows that only an unopposed exact `status
approved` support span can release the bounded sentence “The reviewed source
reports status approved.” This reports a reviewed record, not source truth.
No LLM or provider is called in this qualification.

`D_EFFECT_PATH` and `D_READY_PATH` are fresh absolute files under a private
`0700` directory outside source, package, environment and session roots. The
consumer writes the raw effect with exclusive owner-only creation and fsync.
The test independently derives expected bytes from the pinned external corpus,
reads the installed command's effect file and checks withheld release,
provenance, source IDs, quotes, stances, selected IDs and lexical decisions.
A verifier probe uses a
per-process output path; this is still a synthetic host effect, not an
independent retrieval service or measured answer quality.

The lifecycle test disables the first generation, builds and installs a
separately reviewed 1.0.1 fixture package, stages and normally launches it,
reads the second effect, disables it, and rolls the session back to retained
1.0.0. It then restores both owned source edits. The two versions have the
same finite retrieval semantics; generation rollback does not erase either
effect. Wrong package/install approvals, changed consumer bytes, bad launch
scope, source/corpus drift, stale revision, missing corpus or effect path,
missing contradiction, and denied host approval fail closed in focused tests.

The source-bound D console binder derives the current caller and owns the
generated task-loop edit. The separate bound installed test carries its exact
baseline, modified, package, install and delivery receipts through two off-mode
task IDs in one process, checking separate raw effects and one startup marker.
It rejects duplicate task IDs before startup and an invalid budget at startup
without an effect. The latter is configuration refusal, not exhausted provider
spend. The test disables version 1.0.0, upgrades to an independently reviewed
1.0.1 package, observes its normal command, and rolls the generation back while
retaining both installed environments and restoring both owned source edits.
The pinned consumer remains unchanged; a small fixture host routes each reviewed
task ID to a fresh external effect path before calling it. These effects are
synthetic file readbacks, not a service-level retrieval measurement.

The separate [installed synthetic connected D shadow protocol](retrieval-template-connected-v1.md)
checks source-bound authority and local loopback fallback. This off-mode fixture
does not qualify untrusted target retrievers, arbitrary queries, a generative
answer model, external connected authority, provider operation, answer
correctness, task benefit, interrupted upgrade or
cross-process task deduplication. A real host needs its own retriever and
generation authority, source provenance, raw answer evaluation and retry
ownership before those cells can be promoted. The pure positive handoff test
is a contract exercise, not an installed or measured answer-quality result.

## Quickstart

Ordered commands for a separately reviewed D host with the documented caller
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
jev-integration-evaluator template validate --repo /private/retrieval-host --request /private/d-request.json

# 2. Bind the reviewed console caller, then materialize planner inputs.
jev-integration-evaluator template bind --repo /private/retrieval-host --request /private/d-request.json --binding /private/d-binding.json --out /private/d-bound
jev-integration-evaluator template materialize --repo /private/retrieval-host --request /private/d-bound/template-request.json --out /private/d-render

# 3. Plan, record the baseline, apply the exact bundle and verify it.
jev-integration-evaluator implement-plan --repo /private/retrieval-host --inventory /private/d-render/reviewed-inventory.json --candidate CANDIDATE_ID --spec /private/d-render/implementation-spec.json --out /private/d-bundle
jev-integration-evaluator implement-verify --phase baseline --repo /private/retrieval-host --bundle /private/d-bundle --approve-execution
jev-integration-evaluator implement-apply --repo /private/retrieval-host --bundle /private/d-bundle --approve BUNDLE_DIGEST --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-verify --phase modified --repo /private/retrieval-host --bundle /private/d-bundle --approve-execution --baseline-sha256 BASELINE_RECEIPT_SHA256
jev-integration-evaluator implement-status --repo /private/retrieval-host --bundle /private/d-bundle --trusted-receipt-sha256 MODIFIED_RECEIPT_SHA256

# 4. Configure and install offline. The package request carries the reviewed
#    off-mode configuration and its independently retained digest.
jev-integration-evaluator template package --request /private/d-package-request.json --out /private/d-package-plan.json
jev-integration-evaluator template package-build --plan /private/d-package-plan.json --approve-plan-sha256 PACKAGE_PLAN_SHA256
jev-integration-evaluator template install-plan --package-plan /private/d-package-plan.json --package-receipt /private/d-package-receipt.json --out /private/d-install-plan.json
jev-integration-evaluator template install --plan /private/d-install-plan.json --approve-plan-sha256 INSTALL_PLAN_SHA256
jev-integration-evaluator template install-status --plan /private/d-install-plan.json

# 5. Normal start of the installed `retrieval-host` console in mode off, then
#    independent observation and status.
jev-integration-evaluator template delivery-plan --install-plan /private/d-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --observation /private/d-observation.json --launch-environment /private/d-launch-environment.json --out /private/d-delivery-plan.json
jev-integration-evaluator template deploy --session /private/d-session --plan /private/d-delivery-plan.json
jev-integration-evaluator template deploy --session /private/d-session --scope /private/d-launch-scope.json --approve-scope-sha256 LAUNCH_SCOPE_SHA256
jev-integration-evaluator template observe --session /private/d-session --trusted-session-head SESSION_HEAD_SHA256
jev-integration-evaluator template status --session /private/d-session --trusted-session-head SESSION_HEAD_SHA256

# 6. Disable, upgrade to a separately reviewed and installed generation,
#    roll the generation back, then restore the owned source edit.
jev-integration-evaluator template disable --session /private/d-session --scope /private/d-disable-scope.json --approve-scope-sha256 DISABLE_SCOPE_SHA256
jev-integration-evaluator template upgrade --session /private/d-session --plan /private/d-delivery-plan-v2.json --scope /private/d-upgrade-scope.json --approve-scope-sha256 UPGRADE_SCOPE_SHA256
jev-integration-evaluator template rollback --session /private/d-session --scope /private/d-rollback-scope.json --approve-scope-sha256 ROLLBACK_SCOPE_SHA256
jev-integration-evaluator implement-rollback --repo /private/retrieval-host --bundle /private/d-bundle --approve ROLLBACK_DIGEST
```

The upgrade plan in step 6 is a second `template delivery-plan` result for a
second reviewed host version that went through steps 1 to 4 on its own. A
launch after `template upgrade` and the later `template disable` each need a
new exact scope.

Optional offline synthetic connected shadow, with the finite `retrieval-d-v1`
profile and a host that includes the reviewed `connected_authority.py` loader
before its final scan and binding:

```bash
jev-integration-evaluator template connected-installed-bind --package-plan /private/d-package-plan.json --package-receipt /private/d-package-receipt.json --install-plan /private/d-install-plan.json --install-receipt /private/d-install-receipt.json --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --out /private/d-installed-binding.json
jev-integration-evaluator template connected-plan --install-plan /private/d-install-plan.json --trusted-install-receipt-sha256 INSTALL_RECEIPT_SHA256 --trusted-package-receipt-sha256 PACKAGE_RECEIPT_SHA256 --installed-binding /private/d-installed-binding.json --trusted-binding-sha256 BINDING_SHA256 --observation /private/d-connected-observation.json --launch-environment /private/d-connected-environment.json --host-profile retrieval-d-v1 --out /private/d-connected-plan.json
jev-integration-evaluator template connected-configure --session /private/d-connected-session --plan /private/d-connected-plan.json --approve-plan-sha256 CONNECTED_PLAN_SHA256
jev-integration-evaluator template connected-launch --session /private/d-connected-session --scope /private/d-connected-launch-scope.json --approve-scope-sha256 CONNECTED_LAUNCH_SCOPE_SHA256
jev-integration-evaluator template connected-status --session /private/d-connected-session
jev-integration-evaluator template connected-stop --session /private/d-connected-session --scope /private/d-connected-stop-scope.json --approve-scope-sha256 CONNECTED_STOP_SCOPE_SHA256
```

Connected shadow only observes: the host keeps its deterministic baseline
effect. See the [connected reference](retrieval-template-connected-v1.md) for the signed
references and the fault schedule. No command here contacts a provider,
enables canary or active mode, or measures benefit.

## Parameters and bindings

A launch environment is a JSON object of string values passed with
`--launch-environment`. `template connected-plan` accepts only the names
listed here for the `retrieval-d-v1` profile; any other name, including the
supervisor-injected `D_CONNECTED_REF_SHA256` and `D_AUTH_PUBKEY_SHA256`,
is refused with `connected_host_references_required`. These finite controls
select reviewed host schedules; none grants runtime, egress or activation
authority.

| Name | Where | Allowed values | Default | What refuses |
| --- | --- | --- | --- | --- |
| `template_id`, `template_version`, `backend`, `profile` | template request | `python.bounded-tail-call`, `1.0.0`, `python`, `module-tail-call-v1` | none; required | `template validate` rejects any other value or changed source |
| `version` | binding input | `1.0` | none; required | `template bind` rejects the binding |
| `script` | binding input | `retrieval-host`, a console script declared in `pyproject.toml` | none; required | `Declared console script is absent or ambiguous` |
| `startup_inputs` | binding input | `budget_limits`, `audit_log`, `dependency_plan` and `startup_options`, each naming a zero-argument factory in the console module (`limits`, `audit`, `dependencies`, `options` in the fixture) | none; all four required | `template bind` rejects a missing or drifted factory |
| `configuration`, `reviewed_configuration_sha256` | package request | strict off-mode `{"jev_runtime": {"mode": "off", "credential_ref": null}}` and its digest | none; required | `reviewed_configuration_drift` at package planning; `installed_configuration_drift` at status |
| `console_script` | package request | `retrieval-host` | none; required | package planning rejects a script the host does not declare |
| `JEV_TEMPLATE_WHEELHOUSE` | test input | absolute private wheelhouse directory | unset | unset: the installed test modules skip, which is not evidence |
| `D_CORPUS_PATH` | off-mode and connected launch environment; a required hashed reference when connected | existing absolute private corpus file with the reviewed bytes and revision 7 | none; required | `D_CORPUS_PATH is required`; `reviewed corpus bytes changed`; `stale corpus revision` |
| `D_EFFECT_PATH` | off-mode launch environment of the single-task host | fresh absolute effect file under an owner-private directory | none; required by the consumer | `D_EFFECT_PATH is required`; `retrieval effect path must be fresh` |
| `D_EFFECT_DIRECTORY` | off-mode and connected launch environment of the bound two-task host | owner-private directory; the host derives one effect file per registered task ID | unset: the host uses `D_EFFECT_PATH` | `unregistered retrieval task` for any other task ID |
| `D_READY_PATH` | off-mode and connected launch environment | fresh absolute ready marker; read by the single-task console only | unset: no marker | `connected_host_references_required` for an unlisted name; the bound host writes `ready.txt` in the effect directory instead |
| `D_TASKS` | off-mode and connected launch environment | `two`, `duplicate` | `two` | `connected_host_references_required`; `duplicate` is refused with `duplicate_task_identity` before startup |
| `D_BUDGET` | off-mode launch environment of the test fixture console | `invalid` or unset | unset: two tasks | `invalid` fails startup validation with no retrieval effect; the connected profile does not accept this name |
| `--host-profile` | `template connected-plan` | `retrieval-d-v1` | omitted selects the legacy Alpha profile | `connected_host_profile_binding_mismatch` |
| `D_CONNECTED_REF` | connected launch environment | absolute owner-private signed reference file | none; required | `connected_host_references_required`; `connected_private_reference_invalid`; `connected_plan_or_reference_drift` after a change |
| `D_AUTH_PUBKEY_FILE` | connected launch environment | absolute owner-private public-only P-256 key file | none; required | `connected_host_references_required`; a launch scope naming another key hash is `exact_expiring_connected_scope_required` |
| `SSL_CERT_FILE` | connected launch environment | absolute owner-private trust certificate, pinned by hash | unset | `connected_private_reference_invalid` |
| `TYPESAFE_API_KEY` | supervisor process environment at `template connected-launch` | present and non-empty; the value is never written to a plan or log | unset | `connected_credential_unavailable` before any launch attempt |
| `D_HOLD` | connected launch environment | `0`, `1` | `0` | `connected_host_references_required` |
| `D_HOLD_POINT` | connected launch environment | `pre-commit`, `between-tasks` | `pre-commit` | `connected_host_references_required` for any other value, and for `between-tasks` without `D_HOLD` `1` and `D_RELEASE_PATH` |
| `D_RELEASE_PATH` | connected launch environment | absolute path the operator creates to release a hold | unset | `retrieval_release_required` when held without it; `retrieval_release_timeout` after 15 seconds |
| `D_AUDIT_PATH` | connected launch environment | accepted by the profile; the reviewed fixture host does not read it | unset | `connected_host_references_required` only for an unlisted name |

## Unsupported cases

Each item is refused or left pending by the code and tests named in this
reference; none is silently adapted.

- A console caller that is not a bounded explicit request loop, including a one-shot caller: binding refuses with `bounded explicit request loop`.
- A missing, changed, stale or non-private corpus: `D_CORPUS_PATH is required`, `reviewed corpus bytes changed`, `stale corpus revision`.
- A query, revision or approval outside the reviewed request: `retrieval query, revision or host approval refused`; an unregistered query: `unregistered retrieval query`.
- A selection that drops the contradictory or uncertain passage for a material claim: `selected passages omit material evidence`. Missing or ambiguous provenance: `ambiguous or missing corpus provenance`.
- A repeated task ID: `duplicate_task_identity` before startup. An occupied effect path: `retrieval effect path must be fresh`.
- Releasing answer text while status evidence conflicts or is missing: the consumer emits `withheld_conflict` or `withheld_missing` with a null answer. A provider assessment failure (wrong model, malformed response, timeout) leaves that baseline effect unchanged; a reference revoked between tasks stops the second task before its route and effect.
- Untrusted retrievers, arbitrary queries, a generative answer model, answer correctness and cross-process task deduplication: outside this fixture.
- A requested mode other than shadow at `template connected-plan`: `connected_mode_requires_observed_gate`. Canary and active need separate observed gates.
- A launch environment name or value outside the table above, or a missing required reference: `connected_host_references_required`.
- An installed binding from another host profile: `connected_host_profile_binding_mismatch`.
- A changed reference, source or plan after planning: `connected_plan_or_reference_drift`; a second launch of one session: `connected_launch_already_attempted`.
- Any platform other than Linux x86-64 CPython 3.13 for the installed stages, a missing offline wheelhouse, connected upgrade for this row, provider operation, canary or active mode and measured benefit: not qualified here and recorded as pending.
