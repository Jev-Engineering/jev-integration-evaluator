# Owned Python console delivery session v1

The initial delivery adapter supervises an already verified, installed Python
console application on Linux x86-64 CPython 3.13. It starts one exact installed
console invocation in its owner-private environment, watches independently
specified files, then drains or stops that process. It does not turn an offline
implementation or installation receipt into provider qualification, benefit,
connected execution authority, or a persistent service claim. The default
runtime mode remains `off`.

## Inputs and CLI journey

Complete the reviewed `template bind`, implementation baseline/apply/modified
verification, and `template package`/`package-build`/`install-plan`/`install`
sequence first. Retain the modified and install receipt SHA-256 digests outside
their bundle and environment. The delivery planner rechecks current source,
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
`ready` means an expected ready marker was observed while the owned process was
alive. `integration_reachable` requires a separate expected effect or probe.
For a finite console command, readiness is observed during its bounded
in-flight interval; it is not an always-on health promise. If the process has
already exited, current readiness is false even when its earlier marker remains.

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
owner lock admits one controller at a time. The launch helper waits on a
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
