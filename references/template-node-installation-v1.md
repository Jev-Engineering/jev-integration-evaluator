# Offline Node package and installation adapter v1 (issue #60 checkpoint)

This distinct Linux x86-64 adapter packages an **already applied and externally
verified** `javascript.recipe-c@1.0.0` host into an owned off-mode generation.
It has Python API only at this checkpoint. It does not execute the installed
entrypoint, start a normal package command, connect a provider, or qualify
shadow/canary/active. The separate #56 supervisor still accepts Python console
install receipts only; its Node launch descriptor and independent observations
remain pending. An installed receipt's `launch_status: not_started` is literal.

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
ready/entrypoint/integration file transitions. Planning and validation do not
launch. The descriptor is an input contract for a future #56 Node supervisor;
the current #56 session API remains Python-console-only. A test runs the normal
installed command under an explicit off-mode environment and checks the three
external files after it exits. That direct test has no durable process session,
PID ownership, interruption recovery or upgrade/rollback authority.

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
target, needs the future bounded owner-aware recovery contract. This checkpoint
does not claim rollback or upgrade qualification.

The original ESM and CommonJS component tests stub the upstream source verifier
and prove only the offline npm and owned-generation boundary. A separate native
test, when `JEV_TRUSTED_TYPESCRIPT_PACKAGE` names an existing local TypeScript
5.8.3 package, copies it into disposable tooling and exercises real catalog
materialization, baseline and modified source verification, exact offline
package/install receipts, and the installed normal command for ESM, CommonJS
and TypeScript. It checks a distinct external entrypoint effect file after the
command. The trusted tooling reader verifies the package's declared version;
substitution with 5.9.3 fails closed. These are finite synthetic off-mode
host executions. The #56 supervisor remains Python-console-only; a versioned
Node process lifecycle and independent observation adapter,
interrupted-operation recovery, required full regressions and any connected
authority remain pending before a complete issue #60 claim.
