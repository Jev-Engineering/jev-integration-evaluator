# Versioned integration template catalog v1

`python.bounded-tail-call@1.0.0` is the initial packaged template. It covers the
existing Python A–M recipes at recipe version `1.0` and the documented
`module-tail-call-v1` source grammar. The renderer creates deterministic,
source-bound **planner inputs** outside the target. It does not apply a patch,
install the evaluator into a host, execute a host, connect a provider, activate
a mode, or establish measured benefit.
The initial pins are evaluator `1.3.0.dev12`, runtime model `jev-1.13.0`,
recipe version `1.0`, and renderer `template-renderer-v1`.

## Current input and exact commands

Obtain a **current** reviewed inventory and implementation specification by
the existing discovery, semantic review, binding review and implementation
planning workflow in [executable integrations](executable-integrations.md).
The request contains these two current objects, not copied example IDs or
hashes. Both objects must pass their existing strict schemas and source checks.
The request itself has a strict
[`template-request-v1` schema](../schemas/template-request-v1.schema.json):

```json
{
  "schema_version": "1.0",
  "template_id": "python.bounded-tail-call",
  "template_version": "1.0.0",
  "backend": "python",
  "profile": "module-tail-call-v1",
  "reviewed_inventory": {"...": "current reviewed inventory object"},
  "implementation_spec": {"...": "current source-bound implementation spec object"}
}
```

The placeholder objects above explain the shape; they are not executable
inputs. An operator can combine two already reviewed local JSON files without
copying an example identity by running this Python snippet in a private folder:

```python
from jev_integration_evaluator.io import read_json, write_json

write_json('/private/request.json', {
    'schema_version': '1.0',
    'template_id': 'python.bounded-tail-call',
    'template_version': '1.0.0',
    'backend': 'python',
    'profile': 'module-tail-call-v1',
    'reviewed_inventory': read_json('/private/current-inventory.json'),
    'implementation_spec': read_json('/private/current-spec.json'),
})
```

Then run:

```bash
jev-integration-evaluator template list --json
jev-integration-evaluator template inspect python.bounded-tail-call --version 1.0.0
jev-integration-evaluator template validate --repo /current/host --request /private/request.json
jev-integration-evaluator template materialize --repo /current/host --request /private/request.json --out /new/private/template-render
```

Equivalent Python API: `list_templates()`, `inspect_template(id, version)`,
`validate_template_request(host_root, request)` and
`materialize_template(host_root, request, new_external_output)` from
`jev_integration_evaluator.template_catalog`. The CLI and API return the same
versioned JSON validation/materialization result. API callers can map a caught
input exception with `template_error(exc)` to the same `schema_version: 1.0`,
`status: rejected` JSON envelope the template CLI emits on stderr with exit 2.
Legacy CLI error envelopes are unchanged. The materialized directory
contains `template-manifest.json`, `template-request.json`,
`implementation-spec.json`, `reviewed-inventory.json`, `template-lock.json`
and `render-status.json`. The lock records manifest, request, inventory, spec,
source, policy, renderer and complete evaluator tool digests, resource hashes, recipe identity and a
planner command descriptor. Validate the resource hashes before using these
inputs with `implement-plan`, which still performs its own current source and
policy checks and creates a separate reviewed bundle. Do not infer application
authority from the template lock.

## Compatibility and lifecycle

The manifest declares language, grammar, backend/recipe versions, supported
target profile, host interfaces, dependency/configuration format, env-only
secret references, runtime/task ownership, legal decisions, fallback, evidence
schema and verification schedule. Its lifecycle matrix marks generation
supported, apply pending separate approval, install unsupported by the
renderer, entrypoint reachability pending a host test, connectivity pending
separate authority, authorized mode off, and measured benefit unknown.

The request schema and manifest are major-version contracts. Version `1.0`
refuses unknown keys, unknown template/recipe/backend/profile versions and
legacy requests; no automatic migration is attempted. Keep an older evaluator
wheel and its exact manifest to read older outputs. To upgrade, create a fresh
request against current reviewed source with the new wheel and materialize to
a new directory. Rollback of a rendered template means discard its external
directory; target rollback remains governed by the implementation lifecycle.
The source host can be Linux or local Windows NTFS for the current catalog
materialization checks; this does not qualify installed host deployment on
either platform.

Validation fails before output writes on stale source, source/inventory review
mismatch, unsupported parsed source shape or bindings, occupied adapter path,
invalid policy, malformed parameters,
output inside the host, or a symlink path. A pre-existing output directory is
a collision and is never reused, even for identical inputs. Materialization
first writes `render-status.json` as `incomplete` and changes it to `complete`
last. A crash before the first marker leaves a directory classified by
`render_status(output)` as `incomplete_unmarked`; a complete marker is reported
only as `marker_complete_unverified` because that read-only helper does not
verify resources, current source or host execution. An interrupted render must
be retained for diagnosis or removed by the
owner; choose a new external output directory to retry. Identical validated
inputs and installed tool bytes produce identical resource and lock digests in
two new directories. A source, policy, inventory, recipe, or renderer change
changes or invalidates the binding.

Supported source grammar remains the bounded Python shape in
[executable integrations](executable-integrations.md). Other grammars,
JavaScript/TypeScript templates, native application launch, provider operation
and connected delivery are outside this catalog version. See the manifest's
lifecycle statuses instead of treating generation as deployability.
