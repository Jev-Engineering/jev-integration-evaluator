# Offline Node package and installation adapter v1 (issue #60 checkpoint)

This distinct Linux x86-64 adapter packages an **already applied and externally
verified** `javascript.recipe-c@1.0.0` host into an owned off-mode generation.
Its Python APIs build, install and prepare a read-only Node delivery descriptor.
Planning and status revalidation execute bounded Node/npm version and tooling
probes. These APIs do not launch the installed host, connect a provider, or
qualify shadow/canary/active.
A scoped native test invokes the normal installed command offline and checks
its raw host effect; that test is not a durable #56 supervisor session. The
separate #56 supervisor still accepts Python console install receipts only.
An installed receipt's `launch_status: not_started` is literal.

## Exact inputs and stages

Use the existing [JS source catalog](javascript-recipe-c-template-v1.md) and
`js-plan`, `js-verify`, `js-apply`, `js-verify` lifecycle first. Retain the
modified verification receipt's SHA-256 in an independent channel. The
`node-package-request-v1` object names the **pre-applied host root**, complete
source-stage render directory, JS implementation bundle, that trusted modified
receipt digest, explicit native Node executable and npm CLI file paths and
SHA-256 values, a SHA-256 of the entire npm package module tree, trusted external
TypeScript tooling directory, exact offline
npm cache directory, new package directory, and private generation parent.
Its [schema](../schemas/node-package-request-v1.schema.json) is strict.

The planner checks the render lock and every owned resource, full current
applied source map against the original map plus the reviewed JS generated
files, externally anchored modified JS status, off configuration and secret
reference digests, native Node `v24.18.0`, npm `11.16.0`, exact executable
bytes and all modules loaded by npm, and trusted TypeScript `5.8.3`. The
TypeScript package must reside in an owner-private trusted tooling directory.
The planner hashes its complete package tree, including package metadata and
compiler siblings, into the package plan; status rechecks that tree. A local
test copies an existing TypeScript `5.8.3` package from an operator-specified
`JEV_TRUSTED_TYPESCRIPT_PACKAGE` path into disposable owner-private tooling,
verifies the source and copied tree digests match, and then uses only the copy.
This test source path is provenance for local evidence, not a runtime dependency.
The complete npm package is copied into the private build stage and rehashed before
and after `npm ci`; the launcher file alone is not a sufficient pin. Target `.npmrc`, target compiler config
and plugins are unsupported. A missing trusted compiler fails before output.
The source catalog's lockfileVersion 3 flat-dependency constraints still
apply. The offline cache is bounded and hashed; each lock dependency must be
available there. No network install is attempted. Native binary artifacts
are unsupported.

The API stages are separate:

```python
from jev_integration_evaluator.template_node_installation import (
    plan_node_package, build_node_package, package_status,
    plan_node_install, install_node_package, installation_status,
)
from jev_integration_evaluator.template_node_delivery import (
    plan_node_delivery, validate_node_delivery,
)

package_plan = plan_node_package(reviewed_request)  # read-only
# Review package_plan and retain its exact digest independently.
package_receipt = build_node_package(
    package_plan, approved_plan_sha256=approved_package_plan_sha256)
package_status(package_plan, trusted_receipt_sha256=trusted_package_receipt_sha256)
install_plan = plan_node_install(
    package_plan, package_receipt,
    trusted_package_receipt_sha256=trusted_package_receipt_sha256)  # read-only
# Review install_plan and retain its exact digest independently.
install_receipt = install_node_package(
    install_plan, approved_plan_sha256=approved_install_plan_sha256)
installation_status(install_plan, trusted_receipt_sha256=trusted_install_receipt_sha256)
descriptor = plan_node_delivery(
    install_plan, trusted_install_receipt_sha256=trusted_install_receipt_sha256,
    observation=independently_reviewed_observation,
    launch_environment=reviewed_offline_environment)
validate_node_delivery(descriptor)  # read-only; requires unchanged baselines
```

The two approved digest values must come from the operator's independent
review; the caller supplies the externally retained package and install
receipt digests. Passing a digest read only from the generated output does not
authenticate an approval or receipt.

The separate [`node-delivery-descriptor-v1`](../schemas/node-delivery-descriptor-v1.schema.json)
binds the exact installed Node command and working directory, executable and
entrypoint hashes, generation/source/artifact/configuration/secret-reference
digests, externally retained install receipt digest, and independent expected
ready/entrypoint/integration file transitions. The three allowed output-path
environment values must match their respective observation roles exactly;
linked, protected, traversing or changed outputs fail closed. Planning and
validation may run bounded toolchain probes but do not launch the installed
host. The descriptor is an input contract for the separate bounded Node
supervisor described below; the #56 Python session API remains
Python-console-only. A test runs the normal
installed command under an explicit off-mode environment. Its start script
calls the transformed `seam` and checks `read:x`; the raw host callback writes
the entrypoint effect, followed by separate ready and integration files. The
test checks all three external bytes after exit. Observation paths reject
parent traversal and protected input/generation trees. The launch environment
accepts only the three named fixture output paths, so loader variables such as
`LD_PRELOAD` and `LD_LIBRARY_PATH` are rejected. That direct test is separate
from the durable supervisor path.

## Owned offline Node session checkpoint

`template_node_session` is a distinct Linux x86-64 API. It never passes a Node
receipt to the Python console supervisor. `create_node_session` creates an
owner-private session and saves the exact unlaunched descriptor under its
digest. `launch_node_session` requires a fresh `template-delivery-scope-v1`
whose `plan_sha256` is the **descriptor SHA-256**, `run_id` and trusted journal
head match the session, and `launch` is granted. The scope's digest must also
be supplied independently. The supervisor writes the launch intent, starts a
private waiting helper, records Linux boot ID, PID and process start ticks,
then releases that helper to exec the exact installed Node command. It sets
only a fixed PATH, `JEV_RUNTIME_MODE=off`, and the descriptor's three reviewed
output paths. It does not inherit loader, npm or credential variables.

`observe_node_session` checks the separately declared ready, entrypoint and
integration file hashes. Readiness requires the owned process to be alive at
observation time; recorded observations are historical, while `process_alive`
and `current_installation` are recomputed status. `stop_node_session` drains
for at most 30 seconds, then uses a pidfd to signal only the matching process.
`disable` is durable and a later `stop` cannot undo it. `resume_node_session`
requires the current externally retained journal head. A launch interrupted
before child identity is journaled can be retried with a fresh scope after
the waiting pipe closes; a possibly executed child is never replayed. An
uncertain dead child is `blocked_recovery` until independently reviewed.

`upgrade_node_session` is valid only after stop. It rechecks the old installed
generation, validates a fresh descriptor with independent unused output paths,
and records the new selected generation without launching it. An interrupted
selection resumes under the same run ID and journal. Resume rechecks the
installed generation being left, then verifies that the loaded pending plan's
content digest equals its journal-anchored filename before selecting it. If
either check fails, the pending row and externally retained head remain in
place for review. `rollback_node_session`
requires the exact previous generation digest, a stopped current process and
unchanged retained installation. Rollback recovery repeats that current
generation check and verifies the previous plan against its history digest.
It restores selection only; no source files
or installed bytes are deleted and no process is launched. The previous
descriptor's observation paths were consumed by its earlier run, so rollback
does not by itself authorize another launch. Fresh source rollback stays with
the existing JS lifecycle and its own receipt/scope.

The CLI mirrors these APIs as `template node-delivery-plan`,
`node-session-create`, `node-launch`, `node-observe`, `node-status`,
`node-resume`, `node-stop`, `node-disable`, `node-upgrade`, and
`node-rollback`. Keep session, descriptor, journal head, scope and scope digest
in separately owned channels. Session creation interrupted before its first
journal row leaves an owner-marked root requiring review; markerless or unknown
content is never adopted. The supervisor remains offline and off-mode.

```sh
jev-integration-evaluator template node-delivery-plan \
  --install-plan /private/node-install-plan.json \
  --trusted-install-receipt-sha256 EXTERNALLY_RETAINED_DIGEST \
  --observation /private/node-observation.json \
  --launch-environment /private/node-output-paths.json \
  --out /private/node-descriptor.json
jev-integration-evaluator template node-session-create \
  --session /private/node-session --descriptor /private/node-descriptor.json
jev-integration-evaluator template node-launch \
  --session /private/node-session --scope /private/exact-launch-scope.json \
  --approve-scope-sha256 EXTERNALLY_APPROVED_SCOPE_DIGEST
jev-integration-evaluator template node-observe \
  --session /private/node-session --trusted-session-head EXTERNALLY_RETAINED_HEAD
jev-integration-evaluator template node-disable \
  --session /private/node-session --scope /private/exact-disable-scope.json \
  --approve-scope-sha256 EXTERNALLY_APPROVED_SCOPE_DIGEST
```

The three output paths are unique and owner-private. A new effect action needs
a new scope bearing the latest journal head; an old head is never inferred from
the session itself. `node-resume` requires the same externally retained current
head. `node-upgrade` additionally requires a new descriptor and its digest in
`scope.upgrade_plan_sha256`; `node-rollback` requires the status-reported exact
`previous_generation_rollback_digest` in its separate scope. `node-status` is
read-only and may be called without a trusted head for diagnostics; passing a
head requests an exact match.

The native ESM installed journey also injects two supervisor start faults
against its source-verified installed command. If the waiting child is started
but its identity is not journaled, closing the private release pipe leaves
zero raw output; same-run resume records an unreleased attempt, and a fresh
scope permits one normal installed invocation. If the child identity is
journaled but release fails, resume preserves `blocked_recovery`, refuses a
retry, and no effect or readiness file appears. These are controlled offline
faults before child release. CommonJS and TypeScript have installed normal
command checks, but these two start faults have not run on those formats.

The build writes a durable owner intent in the private parent **before**
creating its output directory. The install stage does the same for its
generation. Status can identify interruption before the directory, between
directory creation and its owner marker, and after the journal starts. The
markerless-directory stage requires an exactly empty, privately owned `0700`
directory on its parent's filesystem. Status also rejects permission or root
identity drift in completed outputs; any content, mount root or dangling root
symlink is an unknown collision. An interruption while writing
the temporary intent, before its atomic rename, fails closed as `ownership
intent precommit incomplete` and needs operator review. Status never adopts or
deletes such a partial root automatically.

The build copies the exact applied source into a new private package directory,
copies the exact offline cache and npm module tree, and runs the pinned native Node/npm pair as
`npm ci --ignore-scripts --offline --omit=dev --no-audit --no-fund` with explicit
cache, empty private user/global npm config, and a fixed minimal environment.
The command uses no shell and never reads inherited `NODE_OPTIONS`, `NODE_PATH`,
`NPM_CONFIG_*` or credential variables. Its stdout/stderr are not persisted.
Every installed application file is hashed after npm. The install stage copies
that exact artifact into a new `jev-node-env-<plan digest>` generation and
records an immutable command vector, working directory, executable and
entrypoint hash, artifact/source/config/secret-ref digests, generation ID,
owner marker and chained journal head. It never runs that command.

## Status, failure and support limits

`package_status` and `installation_status` re-read current source, tools and
owned bytes. They distinguish recorded content from an externally anchored
receipt. A drifted owned file, changed toolchain or altered receipt fails
closed. Build or install interruption leaves an owned root and journal with
`*_interrupted_review_required`; no automatic npm replay or recursive cleanup
occurs. Retain the root for review and choose a new, separately approved output
plan. Removing a completed or partial generation, or adopting it as a launch
target, needs a separate bounded owner-aware recovery contract. This
installation stage itself does not clean up interrupted build/install roots.

The original ESM and CommonJS component tests stub the upstream source verifier
and prove only the offline npm and owned-generation boundary. A separate native
test, when `JEV_TRUSTED_TYPESCRIPT_PACKAGE` names an existing local TypeScript
5.8.3 package, copies it into disposable tooling and exercises real catalog
materialization, baseline and modified source verification, exact offline
package/install receipts, and the installed normal command for ESM, CommonJS
and TypeScript. It checks a distinct external entrypoint effect file after the
command. The trusted tooling reader verifies the package's declared version;
substitution with 5.9.3 fails closed. These are finite synthetic off-mode
host executions. The #56 supervisor remains Python-console-only. The separate
Node session adds bounded offline process ownership and observation. Required
full regressions, installed evaluator CLI three-format journeys, connected
authority, async rejection/cancellation and cross-placement budget coverage
remain pending before a complete issue #60 claim.
