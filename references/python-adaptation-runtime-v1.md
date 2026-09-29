# Generated Python adaptation runtime v1

This is a separate, bounded profile beside the original Python recipe engine
and the v1 one-source adaptation lifecycle. It generates a real adapter module
that uses the host-owned `HostRuntimeLifecycle` and the existing recipe C
assessment contract. It does not turn an adaptation receipt into a verified
implementation bundle for `template package`. The offline package installer
still requires its own verified implementation bundle and full package-source
digest. Do not pass this profile's adapter plan as that bundle.

## Supported source and host contract

The existing `instance-method-tail-call-v1` and `async-module-tail-call-v1`
edits retain their exact receiver and await behavior. The new
`module-fixed-positional-tail-call-v1` grammar admits one undecorated top-level
synchronous function with two to eight required positional parameters and
exactly one `return baseline(p0, ..., pn)` call. Each argument must be the
unchanged corresponding parameter, exactly once and in order. The generated
edit calls `adapter.invoke(baseline, (p0, ..., pn))`; its `binding_map` records
each source and baseline parameter by position. `request_position` identifies
the parameter that contains the host's stable task mapping. Positional-only
parameters are permitted; defaults, variadics, keyword-only parameters,
decorators, nested scopes, branches, loops, multiple statements, reordered or
computed arguments, and dynamic lookup are rejected before writes.

The selected source must already have one unambiguous `import adapter` in a
flat module or `from . import adapter` in a regular package. Adding that import
is a separate prerequisite edit requiring the usual authorized baseline,
fresh scan and review. A package must declare a static `[project.scripts]`
entrypoint in `pyproject.toml`. `inspect_runtime_package` parses every Python
file in the selected regular package and records its direct selected seam
calls, byte hashes, script target, and build configuration hash. Unknown,
dynamic, reassigned, reexported, or ambiguous callers block. The independent
`adaptation-runtime-caller-review-v1` additionally attests that the declared
package is a closed caller scope. Python parsing alone cannot prove that
unseen external callers do not exist.

Host startup supplies real `registry`, `baseline_action`, `evidence`, `gate`,
`validate`, `blocked`, and `guard` callables; a shared budget, audit sink,
offline synthetic client for shadow, and an externally authenticated
post-adaptation review receipt. The generated module creates one
`HostRuntimeLifecycle` and offers `startup`, `invoke`, `invoke_async`,
`complete_task`, and `shutdown`. Startup verifies the adapter bytes, adapted
source, complete caller scope, build configuration, and installed script
metadata. The host passes the final generated adapter plan to `startup`;
the runtime receipt carries both its exact contract digest and the verified
adaptation digest. Startup checks the final plan's self-digest, engine identity,
specification, source, caller scope and generated adapter hash before accepting
the independently authenticated runtime review. Installed wheels check their
installed Python bytes directly;
`pyproject.toml` is bound at build/review time because it may not be in the
wheel. Both regular and `src/` layouts are supported.

Only `off` and offline synthetic `shadow` are admitted. Shadow observes through
recipe C and never changes the original host operation. The async shadow
assessment enters a worker thread, so the event loop does not perform provider
I/O; then the original coroutine is awaited once on its event loop. A
cancelled shadow assessment may finish its already scheduled observation, but
cannot start or replay the original operation. Connected shadow, canary,
active, remote clients and live async benefit remain unsupported pending a
separate bounded qualification. Runtime effects, cost and cache assertions
from offline fixtures are synthetic evidence only.

## Exact staged lifecycle

Use `scripts/prepare_adaptation_runtime.py --help` for the CLI. The public
Python APIs are `plan_generated_adapter`, `apply_generated_adapter`,
`generated_adapter_status`, and `rollback_generated_adapter` in
`integrations.adaptation_adapter_lifecycle`; `inspect_runtime_package` and
`render_adapter` are read-only preparation APIs. Inputs are strict JSON
contracts in `schemas/` with identical packaged copies under
`jev_integration_evaluator/data/`.

```bash
python scripts/prepare_adaptation_runtime.py plan --repo /reviewed/host \
  --request /private/bootstrap-request.json --spec /private/provisional-spec.json \
  --inventory /private/reviewed-inventory.json \
  --caller-review /private/caller-review.json --out /private/new-bootstrap-bundle
python scripts/prepare_adaptation_runtime.py apply --repo /reviewed/host \
  --bundle /private/new-bootstrap-bundle --approve EXACT_PLAN_DIGEST \
  --trusted-caller-review-sha256 EXTERNALLY_RETAINED_REVIEW_DIGEST
python scripts/prepare_adaptation_runtime.py status --repo /reviewed/host \
  --bundle /private/new-bootstrap-bundle
# After source adaptation, native verification, fresh rescan and review:
python scripts/prepare_adaptation_runtime.py plan --repo /reviewed/host \
  --request /private/final-request.json --spec /private/fresh-adapted-spec.json \
  --inventory /private/fresh-reviewed-inventory.json \
  --caller-review /private/fresh-caller-review.json --out /private/new-final-bundle \
  --trusted-adaptation-verification-sha256 EXTERNALLY_RETAINED_VERIFICATION_DIGEST
python scripts/prepare_adaptation_runtime.py rollback --repo /reviewed/host \
  --bundle /private/new-final-bundle --approve EXACT_OPERATION_ROLLBACK_DIGEST
```

The `plan` result contains `contract_digest`, `rollback_digest`, final adapter
hash and caller-scope hash. `status` reports only local byte/journal state.

1. Start with an approved source-matched inventory and an exact existing
   static import. `plan ... --request bootstrap.json --spec provisional-spec.json
   --inventory reviewed.json --caller-review caller-review.json --out NEW_BUNDLE`
   generates only an adapter **creation** patch. The provisional spec binds
   the projected adapted file hash. Keep the plan and independent caller
   review digests outside the target. `apply --repo HOST --bundle NEW_BUNDLE
   --approve PLAN_DIGEST --trusted-caller-review-sha256 REVIEW_DIGEST` creates
   only the generated adapter file. The legacy unedited seam still runs its
   baseline; no runtime startup is authorized by adapter creation.
2. Rescan/review the current package including the generated adapter. Use the
   existing `plan_adaptation`, `apply_adaptation`, and
   `verify_adaptation` lifecycle for the one selected seam source. Its native
   baseline and modified receipts must be independently anchored. The
   adaptation plan owns the source; the bootstrap plan owns the adapter.
3. Rescan the **adapted** bytes and repeat semantic, policy, source, and caller
   review. The final request has `stage: "final"`, the exact original and
   adapted file hashes, `request_position`, `positional_count`, and
   `adaptation_verification_sha256`. The final spec must carry the fresh
   adapted symbol hash, not the pre-edit symbol hash. Pass the independently
   retained verification digest through
   `--trusted-adaptation-verification-sha256` when planning the final adapter
   revision. Apply that exact plan under a fresh caller review. Host startup
   requires a separate authenticated `adaptation-runtime-review-receipt-v1`
   binding the final adapter plan and adaptation verification digests, final
   adapter bytes, adapted file and symbol hashes, caller scope, build
   configuration and script target. The host supplies that final plan as
   `adapter_plan` at `startup`.
4. Run the normal installed command with the runtime defaulting to `off`, then
   an explicitly selected offline synthetic shadow schedule. Close each
   stable task once and shut down in `finally`. A later template or runtime
   plan must be made from a fresh adapted-source inventory and its own
   applicable receipt; neither earlier approval carries forward.

For rollback, restore the final adapter revision first, then use the legacy
adaptation rollback for the exact owned source, then remove the bootstrap
adapter with its operation-specific rollback digest. Each stage refuses owned
byte or mode drift. Keep all private bundles and preimages until recovery is
complete. A local `applied_unverified` status does not authenticate a native
execution or authorize activation. Interrupted or inconsistent journal state
is `blocked_recovery` and needs exact owned-state reconciliation.

## Diagnostics and exclusions

`Invalid generated adapter request`, `Bootstrap source differs from reviewed
bytes`, `Independent complete-caller review must bind exact package audit`,
`Final adapter spec requires fresh adapted source review`, and `Externally
anchored verified adaptation required before final runtime` stop before a
target write. Startup rejects changed source, adapter, build configuration or
installed console metadata before a selected operation. Unknown external
callers, non-regular packages, dynamic imports, callback registries,
framework autoloading, nested package seams, multiprocess/distributed budget
ownership and connected async execution are unsupported.

RAG retrieve-then-generate remains a two-stage profile; claim-check
assignment/return still lacks a disposition consumer. Graph approval/revision
branches, agent retry loops and retention branches are not rewritten by this
tail-call profile. A separately documented host contract may support some of
those workflows; this adapter cannot infer their policy or consumer semantics.
