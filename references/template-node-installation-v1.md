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
SHA-256 values, trusted external TypeScript tooling directory, exact offline
npm cache directory, new package directory, and private generation parent.
Its [schema](../schemas/node-package-request-v1.schema.json) is strict.

The planner checks the render lock and every owned resource, full current
applied source map against the original map plus the reviewed JS generated
files, externally anchored modified JS status, off configuration and secret
reference digests, native Node `v24.18.0`, npm `11.16.0`, exact executable
bytes, and trusted TypeScript `5.8.3`. Target `.npmrc`, target compiler config
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

package_plan = plan_node_package(reviewed_request)  # read-only
# Review package_plan and retain its exact digest independently.
package_receipt = build_node_package(
    package_plan, approved_plan_sha256=approved_package_plan_sha256)
package_status(package_plan, trusted_receipt_sha256=trusted_package_receipt_sha256)
install_plan = plan_node_install(package_plan, package_receipt)  # read-only
# Review install_plan and retain its exact digest independently.
install_receipt = install_node_package(
    install_plan, approved_plan_sha256=approved_install_plan_sha256)
installation_status(install_plan, trusted_receipt_sha256=trusted_install_receipt_sha256)
```

The two approved digest values must come from the operator's independent
review; the caller supplies the externally retained package and install
receipt digests. Passing a digest read only from the generated output does not
authenticate an approval or receipt.

The build copies the exact applied source into a new private package directory,
copies the exact offline cache, and runs the pinned native Node/npm pair as
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

ESM and CommonJS native offline component tests exercise actual pinned npm
build and owned install with a stubbed *upstream source verifier* because
TypeScript 5.8.3 is unavailable in this local runner. The test proves the
effect boundary and drift checks, not a complete source-verified journey. The
real planner rejects missing TypeScript 5.8.3. A fresh full source-bound
ESM/CommonJS/TypeScript installed and normal-entrypoint journey, #56 Node
descriptor, interrupted-operation recovery, required regressions and any
connected authority remain pending before a release claim or PR publication.
