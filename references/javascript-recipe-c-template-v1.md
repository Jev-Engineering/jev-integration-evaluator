# JavaScript recipe C template catalog v1

`javascript.recipe-c@1.0.0` is a separate, source-bound catalog entry for the
existing native JS/TS recipe C backend. This release stage materializes planner
inputs only. It does not apply edits, install npm packages, launch a host,
connect a provider, activate a mode, or establish benefit. The Python template
request and legacy `template` commands retain their original contracts.

## Declared input

The private request must satisfy
[`javascript-template-request-v1`](../schemas/javascript-template-request-v1.schema.json).
It names exactly one `.mjs`, `.cjs` or `.ts` reviewed implementation spec,
one finite `node start.mjs` or `node start.cjs` package script, SHA-256 digests
of `package.json`, `package-lock.json`, and the start entrypoint, plus an
independently reviewed digest of the complete bounded package source file map.
The source map includes every regular host file except top-level `.git`,
`node_modules` and Python test caches; it is limited to 4096 files and 64 MiB. The selected
source, entrypoint and both package files must be present. Added or changed
files invalidate the reviewed digest.
Configuration has only `mode: off` and an optional `env:NAME` credential
reference; the declared secret-reference map must match it exactly. No secret
value is read by the catalog.

`package-lock.json` must be lockfileVersion 3 and agree with the package root.
This first catalog profile permits a flat, fully locked production dependency
set with exact versions, SHA-512 integrity and HTTPS tarballs. It rejects root
lifecycle/build scripts and dependency lock rows declaring `hasInstallScript`,
plus workspaces, links, optional/development and transitive dependency graphs.
The catalog does **not** inspect tarball `package.json` files, so an absent or
misdeclared lock hook flag does not prove a dependency has no install hook.
The future installer must run `npm ci --ignore-scripts` or independently inspect
the exact approved tarballs before effects. Native dependency builds remain
outside this profile. These are machine-checked source restrictions, not an
assertion that arbitrary npm projects are safe. The entrypoint file
is source-bound, but reachability is pending a separately authorized launch
test. A package script declaration alone is not runtime evidence.

The validator calls the existing `js_lifecycle` source checker and trusted
TypeScript 5.8.3 transformer with an absolute tooling directory outside the
target. It never reads target `tsconfig`, target plugins, or target compiler
packages, and it does not import or execute target modules. The trusted Node
binary, compiler and backend file hashes appear in the materialization lock.
All source paths reject symlinks and traversal.
The install adapter must separately pin npm and the exact supported Node
version before release; a catalog lock by itself does not qualify either.

## Commands and artifacts

Given a reviewed request at `/private/request.json`, a current target at
`/host`, and a trusted tooling directory at `/trusted/tooling`:

```bash
jev-integration-evaluator template inspect javascript.recipe-c --version 1.0.0
jev-integration-evaluator template validate --repo /host --request /private/request.json --tooling /trusted/tooling
jev-integration-evaluator template materialize --repo /host --request /private/request.json --tooling /trusted/tooling --out /private/new-render
```

Equivalent API: `validate_template_request(root, request,
tooling_dir=trusted)` and `materialize_template(root, request, new_output,
tooling_dir=trusted)`. `template list` includes the JS entry after the
unchanged Python entry. Materialization creates an exclusive owner-private
directory outside the target with `template-manifest.json`,
`template-request.json`, `implementation-spec.json`, `package-profile.json`,
`template-lock.json`, and `render-status.json`. The lock has an exact
`js-plan` descriptor, resource hashes, format, source/config/secret digests,
generated/TypeScript emitted source hashes, and trusted tooling identity.
Revalidation of current source and tools precedes any output write. A partial
render is retained as incomplete; an occupied output is never adopted.

Use the existing `js-plan`, `js-verify`, `js-apply`, `js-status`, `js-recover`,
and `js-rollback` commands for reviewed source edits and verified entrypoint
cases. The catalog lock grants none of their execution or mutation authority.
The [separate offline Node package/install adapter](template-node-installation-v1.md)
binds the exact applied source, package/lock, artifact, config/secret refs and
an owned off-mode generation through independent approvals. Its initial native
component tests stub the upstream source verifier because trusted TypeScript
5.8.3 is absent locally; installed end-to-end qualification remains pending. The #56
delivery supervisor will separately govern launch, status, stop, upgrade and
rollback. Until those gates are implemented and tested, these lifecycle rows
remain pending in the manifest. Connected modes require their own exact
authority, receipt and observed holdout gates. Synthetic JS verification is
neither provider connectivity nor observed benefit.

The declared target is Linux x86-64, single process. Browser, worker and
multi-process budget claims, yarn/pnpm/Bun, target compiler configuration,
arbitrary bundlers/frameworks, unsupported JS source shapes and A–M recipes
other than C are outside this entry. An incompatible request, manifest or
lock needs explicit migration; rerender against current source for an upgrade.
