# Owned Python console delivery session v1

The initial delivery adapter supervises an already verified, installed Python
console application on Linux x86-64 CPython 3.13. It starts one exact installed
console invocation in its owner-private environment, watches independently
specified files, then drains or stops that process. It does not turn an offline
implementation or installation receipt into provider qualification, benefit,
connected execution authority, or a persistent service claim. The default
runtime mode remains `off`.

## Inputs and CLI journey

Begin a stable run with `template journey-create` after the source-bound
implementation or composite plan exists and before apply. Run the reviewed
`template bind`, baseline/apply/modified verification, and `template package`/
`package-build`/`install-plan`/`install` commands through their own exact
authorization contracts. After each stage, `template journey-record` pins its
plan or externally retained receipt to the same `run_id` and journal head.
`template journey-status` only reconciles the current owned bytes and returns
an exact next action; it never repeats an uncertain apply, build or install.
For a pending apply use the existing `implement-status`/`implement-rollback`
or composite equivalents. For an interrupted package or environment, use the
exact #55 `package-recover` or `install-recover` approval and generation digest.
`template journey-promote` creates the runtime session under
`<journey>/runtime` with the same run ID once installation is verified. It
does not launch the host. The journey state is
[`template-delivery-journey-v1`](../schemas/template-delivery-journey-v1.schema.json)
and has a separate owner-private hash-chain journal. This is a bridge between
existing effect owners, not a second executor.
If promotion stops before the child journal's first row, `journey-status`
returns `recover_exact_unlaunched_runtime` only when all existing child bytes
match the expected pre-launch create prefix. Use
`template journey-recover-promotion --session ... --trusted-journey-head ...`
with the externally retained current journey head. Unknown files, changed
plans, a nonempty torn child journal, or a different run identity block
recovery. The recovery event is recorded under the original run ID.
If the child `created` row is durable but the outer completion row is absent,
`journey-status` returns `complete_exact_promotion`. Repeat `journey-promote`
with the current externally retained journey head and the identical observation
and launch environment; it validates the existing child and records completion
without launching it.

```bash
jev-integration-evaluator template journey-create \
  --session /private/journey --source-root /private/host \
  --bundle /private/implementation-bundle --source-kind single
# After the separately authorized source baseline verification:
jev-integration-evaluator template journey-record \
  --session /private/journey --trusted-journey-head LAST_RETAINED_HEAD \
  --stage baseline_anchored --trusted-receipt-sha256 EXTERNAL_BASELINE_RECEIPT_SHA256
# Repeat journey-record for source_verified, package_planned, package_built,
# install_planned, and installed after their underlying effect owners finish.
jev-integration-evaluator template journey-status \
  --session /private/journey --trusted-journey-head LAST_RETAINED_HEAD
jev-integration-evaluator template journey-promote \
  --session /private/journey --trusted-journey-head LAST_RETAINED_HEAD \
  --observation /private/observation.json
```

`package_planned` and `install_planned` require `--plan` with the exact plan
JSON. `package_built` requires `--receipt` and
`--trusted-receipt-sha256`; `source_verified` and `installed` require the
trusted receipt digest. Record each new `journey_head_sha256` externally before
the next call. Old receipts remain in the journey history after a later
generation is stopped or the owned source is rolled back. A source or package
drift result blocks dependent stage advancement.

Retain the modified and install receipt SHA-256 digests outside their bundle
and environment. The delivery planner rechecks current source,
configuration, secret references, package files and installed receipt through
the installer; a changed or unavailable prerequisite fails closed. A local
receipt digest is not its own trust anchor.

Write an observation JSON file matching
[`template-delivery-observation-v1`](../schemas/template-delivery-observation-v1.schema.json).
The [offline fixture example](../examples/template-delivery-observation.json)
shows the shape and hashes of literal `ready\n` and `first\n` bytes; replace
both paths and expected bytes with the independently reviewed host contract.
Each check states a role, absolute external regular-file path, its current
SHA-256 or `null` if absent, and a distinct expected SHA-256. The checks come
from an independent host contract, not the generated adapter's success output.
Plans must schedule `ready`, `entrypoint_reached`, and
`integration_reachable`; the ready and integration checks use different paths.
`ready` means an expected ready marker was observed while the owned process was
alive. `integration_reachable` requires a separate expected effect or probe.
For a finite console command, readiness is observed during its bounded
in-flight interval; it is not an always-on health promise. If the process has
already exited, current readiness is false even when its earlier marker remains.
The process identity is checked again after matching ready bytes, though
the observation remains a bounded sample rather than atomic service health.
`mode_authorized` records approval of the requested `off` launch. It does not
measure the target's effective mode. The supervisor reserves `JEV_*` runtime
variables from caller supplied launch environment and sets `JEV_RUNTIME_MODE`
to `off` after adding permitted host parameters.
In the composite offline fixture, `integration_reachable` and
`outcome_verified` are separate recorded fields derived from the same second
raw effect file; they are not independent outcome probes. The two placement
effects themselves use distinct files and are checked separately.

```bash
jev-integration-evaluator template delivery-plan \
  --install-plan /private/install-plan.json \
  --trusted-install-receipt-sha256 EXTERNALLY_RETAINED_INSTALL_RECEIPT_SHA256 \
  --observation /private/observation.json --out /private/delivery-plan.json
jev-integration-evaluator template deploy \
  --session /private/delivery-session --plan /private/delivery-plan.json
jev-integration-evaluator template deploy \
  --session /private/delivery-session --scope /private/launch-scope.json \
  --approve-scope-sha256 EXTERNALLY_APPROVED_SCOPE_SHA256
jev-integration-evaluator template observe \
  --session /private/delivery-session --trusted-session-head LAST_RETAINED_HEAD
jev-integration-evaluator template status \
  --session /private/delivery-session --trusted-session-head LAST_RETAINED_HEAD
jev-integration-evaluator template disable \
  --session /private/delivery-session --scope /private/disable-scope.json \
  --approve-scope-sha256 EXTERNALLY_APPROVED_SCOPE_SHA256
```

`deploy --plan` creates the private journal and plan archive without running
the host. Its returned `run_id`, `plan_sha256` and `session_head_sha256` bind
the next scope. A scope matches
[`template-delivery-scope-v1`](../schemas/template-delivery-scope-v1.schema.json):
it names the run and plan, the externally retained current head, an expiry,
revocation state and explicit grants for each operation. The operator must
retain the scope and journal head independently. A stale head, expired or
revoked scope, or absent grant blocks the dependent action; the session never
prompts for an approval that its existing valid scope already covers.

The public API is `plan_delivery`, `create_session`, `launch_session`,
`resume_session`, `observe_session`, `session_status`, `stop_session`,
`upgrade_session`, and `rollback_session` in
`jev_integration_evaluator.template_delivery`. CLI actions are
`delivery-plan`, `deploy`, `resume`, `observe`, `status`, `stop`, `disable`,
`upgrade`, and `rollback`. All effects require exact scope approval except
`resume`, which only reconciles a prior recorded intent and never replays a
possibly executed invocation. `status` is read-only.

## Evidence and recovery

The owner-private session contains `events.jsonl`, an append-only fsynced
hash-chain, and immutable `plans/<plan_sha256>.json` archives. A nonblocking
owner lock admits one controller at a time. Its parent directory must also be
owner-private. The launch helper waits on a
private pipe until its boot ID, PID and Linux process start ticks are durable;
EOF before release prevents execution. If release may have happened and the
exact process cannot be proven live, recovery records an unknown outcome and
refuses replay. Stop uses a pidfd and the saved identity, a bounded drain and
SIGTERM only for the exact process; pending-stop recovery may repeat that
termination request against the same proven process. A still-live process remains pending
for review; no later stage is inferred from an exit code.

The result keeps `generated`, `applied`, `installed`, `launched`, `ready`,
`entrypoint_reached`, `integration_reachable`, `provider_reachable`,
`mode_authorized`, and `outcome_verified` as separate recorded observations.
`current_process_alive`, `current_ready`, `current_integration_reachable` and
`current_installation` are rechecked by `status`. Recorded history may remain
true after current health has gone false. `provider_reachable` stays false.
`mode_authorized` becomes true only for a scope-approved off-mode launch,
and `provider_qualification` is `not_run`; #57 covers authorized connected
qualification. `observed_benefit` remains false without a separate adoption
measurement.

If `resume` reports `launch_unreleased`, supply a fresh exact launch scope
bound to the new head. If it reports unknown launch effects, inspect the host
effect sink and process outside the session before any new invocation. An
interrupted implementation apply or package/install stage uses its own
`implement-status`/`implement-rollback` or `package-recover`/`install-recover`
contract first; the delivery plan requires those stages to be verified.

## Upgrade and rollback

`upgrade` requires a stopped old generation, a new source-bound and verified
installed plan, and a scope containing `upgrade_plan_sha256`. It archives the
new plan and selects it without starting it. Supply a fresh launch scope to
run the new generation. The old environment and receipt remain for rollback.
An incompatible delivery schema, stale receipt, active old process or reused
environment blocks upgrade. `rollback` after a stopped generation requires
the exact returned `previous_generation_rollback_digest` in its scope; it
selects the retained old verified generation without launching it. On the
first generation, rollback delegates to the exact owned #54 source rollback
digest and refuses concurrent edits; it retains the historical installed
environment. `disable` stops the console under the offline policy and records
that state. The installed source's configured baseline or block fallback is
checked by the existing implementation verification, not altered by disable.

The qualified adapter is a local Python console with an owner-selected finite
observation contract. Generic daemons, Windows, cloud deployment, service
registration, arbitrary network endpoints and production provider authority
are outside this version. A later Node adapter must supply its own exact
installation and executable provenance before the supervisor can accept it.

The composite variant accepts a `template-composite-install-plan-v1` and its
externally anchored composite install receipt. Its source transaction remains
the one owned #54 composite bundle: `status_composite` authenticates the
modified receipt and `rollback_composite` restores exactly that bundle under
its rollback digest. Two reviewed recipe C placements can share one normal
console startup, one lifecycle/coordinator and task identity. The offline
installed fixture checks distinct raw effects for both placements plus a
separate ready marker. Source-level combined verification checks the shared
budget and cross-placement failure behavior; this is not a connected provider
or measured-benefit claim.
