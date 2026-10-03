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

The installed evaluator CLI exposes the same separate package and install stages:
`template node-package-plan --request REQUEST --out PLAN`,
`node-package-build --plan PLAN --approve-plan-sha256 APPROVED_DIGEST`,
`node-package-status --plan PLAN --trusted-receipt-sha256 RETAINED_DIGEST`,
`node-install-plan --package-plan PACKAGE_PLAN --package-receipt PACKAGE_RECEIPT
--trusted-package-receipt-sha256 RETAINED_DIGEST --out INSTALL_PLAN`,
`node-install --plan INSTALL_PLAN --approve-plan-sha256 APPROVED_DIGEST`, and
`node-install-status --plan INSTALL_PLAN --trusted-receipt-sha256 RETAINED_DIGEST`.
The plan commands write new private files exclusively; `node-package-build`
and `node-install` are the only package/install effect commands, and the
separately approved `node-package-recover` and `node-install-recover`
described below are the only commands that remove an interrupted owned root. Keep each
approval and receipt digest in a separately owned channel, and pass the
current digest back explicitly. Installed CLI tests exercise these exact
commands before creating delivery descriptors and launching separate ESM,
CommonJS and TypeScript hosts. The CommonJS and TypeScript cases use their
source-verified fixture builders to obtain already-applied hosts, then make
fresh CLI-owned package and install generations. They pin native Node/npm and
a disposable copy of trusted TypeScript 5.8.3, pass explicit plan and receipt
digests across each CLI stage, and check independent effect, ready and
integration bytes from the normal installed off-mode command. Wrong build,
install and launch approval digests fail before output or host effect appears.
These checks do not exercise provider traffic or qualify connected operation.

The CLI mirrors the session APIs as `template node-delivery-plan`,
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
faults before child release. The installed TypeScript upgrade journey injects
the first of them: its first launch is interrupted before the child identity
is journaled, no observation file appears, the stale scope and a wrong head
are refused, same-run resume returns to `created` with the installed `host.ts`
and compiled `host.mjs` bytes unchanged, and a fresh scope starts the second
attempt once. The journaled-identity release fault has not run on TypeScript,
and neither start fault has run on CommonJS, whose installed fault is the
interrupted upgrade selection.

The independent [installed CommonJS journey](../tests/test_node_template_installed_commonjs.py)
uses a separate named package and two reviewed `host.cjs` versions. Each
`package.json` declares `node start.cjs`; the installed generation's exact
entrypoint and host file hashes match the applied source and are outside the
evaluator checkout. The `original` function calls the fixture callback installed
by `start.cjs`; that callback writes the raw `read:alpha` or `read:beta:v2`
file during the normal installed command. Separate ready and integration files
follow the host effect. The test binds the exact native
Node/npm and trusted TypeScript bytes, source verification, package/install
receipts, descriptor and scope digests. An injected interruption after the
upgrade intent resumes under the same run ID without a second old effect or
an early new effect. Disable and exact selection rollback retain both
generations and both historical effects; owned JS source rollback restores
the reviewed pre-edit files. The ESM child-release fault cases remain separate.

The separate [independent ESM fixture](../tests/independent_hosts/esm_recipe_c/README.md)
pins two complete source/package versions before materialization. Its installed
evaluator CLI materializes the 1.0.0 source from an offline wheel, and the
normal installed `node start.mjs` command reaches the transformed `seam` under
the off-mode supervisor. Version 1.0.1 changes the actual `host.mjs` return
and host callback argument. Independent raw files record `read:alpha` and
`read:beta:v2`, with separate live ready and integration checks. The journey
retains both exact installed generations and receipts, rejects source drift
before upgrade, resumes a pre-release interrupted start under the same run ID,
disables the new generation and selects the old generation with the exact
rollback digest. Both reviewed source trees are then restored through their
owned JS rollback digests. This is a bounded offline ESM fixture, not
connected provider or measured benefit evidence.

The [installed TypeScript upgrade journey](../tests/test_node_template_installed_upgrade.py)
uses two separately reviewed fixture packages, versions 1.0.0 and 1.0.1.
The 1.0.1 `host.ts` changes the finite `original` function called by the
reviewed one-tail-call `seam`: it appends `:v2` to the returned value and raw
effect argument. The generated `host.mjs` has different compiled bytes. Both
versions retain the registered `read` action and off-mode policy. Their normal
`start.mjs` commands check the respective seam result, and their distinct
external raw effects come from the host function.
The test pins the trusted TypeScript 5.8.3 source tree digest
`774ce18bba737b3bbaffec66946dfd9948afaac993cf7e8e3ece871536d6e42b`,
copies it into a fresh private tooling directory and binds its complete tree
digest, the exact Node 24.18.0
and npm 11.16.0 bytes, source review, baseline/modified verification receipts,
offline package/install receipts and fresh external observation paths. The
first installed command is observed and stopped before an exact new descriptor
is selected. The second installed command produces its distinct raw effect
under the same session run ID. Wrong receipt/scope digests, source drift and
installed entrypoint drift refuse before the new launch. After disabling the
second generation, exact rollback selects the retained first installation;
both owned JS source edits are then restored by their separate rollback
digests. Both installed generations and their historical effects remain.
The first generation's consumed observation paths do not permit a replay
after rollback. These versions are synthetic and preserve the same finite
action policy; this does not prove a production migration, provider access,
connected modes, or measured benefit.

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
occurs. Status never removes anything, and a retried `node-package-build` or
`node-install` over an interrupted root is refused. Removing a completed
generation, or adopting a partial one as a launch target, is not supported.

## Owned recovery of an interrupted build or install

Removing an interrupted, never completed owned root is a separate effect with
its own review plan and approval digest:

```python
from jev_integration_evaluator.template_node_installation import (
    plan_node_package_recovery, recover_node_package,
    plan_node_install_recovery, recover_node_installation,
)

recovery_plan = plan_node_install_recovery(install_plan)  # read-only
# Review recovery_plan and retain its exact recovery_sha256 independently.
recovery_receipt = recover_node_installation(
    install_plan, recovery_plan,
    approved_plan_sha256=approved_install_plan_sha256,
    approved_recovery_sha256=approved_recovery_sha256)
```

The CLI forms are `template node-package-recovery-plan --plan PACKAGE_PLAN
--out RECOVERY_PLAN`, `node-package-recover --plan PACKAGE_PLAN --recovery-plan
RECOVERY_PLAN --approve-plan-sha256 APPROVED_PLAN_DIGEST
--approve-recovery-sha256 APPROVED_RECOVERY_DIGEST`, and the same pair as
`node-install-recovery-plan` and `node-install-recover` with the install plan.
The plan command writes one new private file and changes nothing else.

The strict [`node-recovery-plan-v1`](../schemas/node-recovery-plan-v1.schema.json)
binds the interrupted step's plan digest, the owned root path derived from
that plan, the parent-side ownership intent digest, the interruption stage
(`intent_recorded`, `directory_created`, `owner_marked` or `journal_recorded`),
the root directory's device and inode, the interrupted journal rows, the
current head of the recovery journal, and a digest over every entry under the
root: each file's SHA-256, each directory's mode and each link's text. The
recovery digest differs from the step's plan digest, so neither approval can
stand in for the other.

`node-*-recover` requires the same exact step plan and its approval digest,
revalidates that plan as the interrupted step did (source, cache, toolchain
and, for an install, the externally retained package receipt), takes the
step's own lock without waiting, and recomputes the recovery plan. It refuses
when:

- no ownership intent is recorded for this plan and root (nothing was
  interrupted, or the root was never created by this plan);
- a package or install receipt is present (the step completed);
- the journal, owner marker, intent or step plan digest differs, a journal row
  is torn or unknown, or the recovery journal changed since review;
- the root's device, inode, owner, `0700` mode, any file byte, entry name,
  directory mode or link text differs from the reviewed plan;
- the root, a top-level entry, the intent or the recovery journal is a
  symlink, the recovery plan names another root, or the root holds an
  unrelated top-level name, a mount, a special file or a hard-linked file;
- another build, install or recovery holds the lock.

Every refusal leaves all bytes in place. On approval it appends
`recovery_started` to the parent-side `.jev-node-recovery-<root digest>.jsonl`
with a copy of the interrupted journal rows, stage, intent digest and entry
digest; removes the content of that one root with the owner marker and journal
last; appends `recovery_complete`; and finally removes the ownership intent. No
path outside the root, its intent and that recovery journal is written, and
npm is not run. In an install generation, which is a plain copy, any link is
refused. In a build stage a link below a top-level entry (npm may create
`node_modules/.bin` links) is reviewed as link text and unlinked; its target
is never read, followed or removed. Other generations in the same parent,
their receipts and any session that selects them are not opened for writing.

The strict [`node-recovery-receipt-v1`](../schemas/node-recovery-receipt-v1.schema.json)
reports `owned_incomplete_package_removed` or
`owned_incomplete_generation_removed`, the recovery digest, the interrupted
journal head and the recovery journal head. Afterwards status reports
`absent` with `recovered_attempts` and `recovery_journal_head`. The recovery
journal is hash-chained and is never truncated; a missing, reordered, edited
or torn row fails status and further recovery closed. The same step plan may
then be approved and run again as a fresh attempt; a consumed recovery plan
cannot be replayed because the recovery journal head it reviewed has moved.

An interruption of the recovery itself leaves a state that status still
classifies as interrupted (content partly removed with marker and journal
present, an empty owned directory, or only the intent). The earlier recovery
plan no longer matches; a newly reviewed recovery plan finishes it, and the
unfinished `recovery_started` row stays in the history.

Still not covered: recovery is not automatic and is never chosen by status or
by a retry. A completed step, a root with no intent, an intent interrupted
before its atomic rename (`ownership intent precommit incomplete`), a torn
journal row, drifted source, cache, toolchain or package bytes (the step plan
no longer revalidates), content that changes after review, and hard links,
mounts or special files all stay refused for operator review. Durability
across machine power loss or filesystem failure has not been exercised: the
intent and each journal row are flushed with `fsync`, but copied owned content
is not, and a state that does not validate afterwards is refused, not
repaired. Removal assumes no other process
of the same user modifies the root while the lock is held. No interrupted
real `npm ci` child process was produced in tests: the always-on cases
interrupt the real build immediately before npm starts and the real install
before its completion record, and the installed case interrupts a real install
with the pinned toolchain. Interrupted starts are handled by the separate
session resume described above, not by this recovery.

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
full regressions, connected
authority, async rejection/cancellation and cross-placement budget coverage
remain pending before a complete issue #60 claim.

The native runtime test `separate native processes cannot reset a held ledger
or replay its settled effects` exercises two actual Node 24.18.0 processes
against one private durable ledger. The peer is refused while the first owner
holds the SQLite exclusive lock. After release, the peer retains the original
charge and settled invocation tombstone, consumes the last reservation, and
refuses further calls; the original process then observes the exhausted budget.
This is offline ledger contention evidence. It does not establish concurrent
distributed execution, installed cross-package composition, provider operation,
or a selected installed application effect.
