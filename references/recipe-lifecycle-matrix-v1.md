# Recipe lifecycle matrix v1 (issue #59, acceptance criterion 4)

This inventory gives every Python recipe A–M and the separate JavaScript/TypeScript
recipe C catalog entry one explicit cell per lifecycle stage and per platform.
The [machine-readable matrix](../jev_integration_evaluator/data/recipe-lifecycle-matrix-v1.json)
has exactly 14 rows and is validated by the strict, mirrored
`recipe-lifecycle-matrix-v1` schema. `recipe_lifecycle_matrix()` in
`jev_integration_evaluator/recipe_lifecycle.py` reads it, checks the rows
against the Python recipe catalog and the packaged JavaScript manifest, and
refuses a missing row, an omitted cell or a qualified observed-only stage.
[`tests/test_recipe_lifecycle_matrix.py`](../tests/test_recipe_lifecycle_matrix.py)
runs on every platform without gating.

It is a read-only description of test coverage in this repository. It grants no
implementation, installation, runtime, egress or provider authority. The
Python catalog status `implemented_bounded_shape` means only that the narrow
`module-tail-call-v1` transform exists; it is not an installed qualification.
The [use-case matrix](use-case-template-matrix-v1.md) remains the source-bound
record for the six pinned use-case fixtures.

## Cell values

| Value | Meaning |
| --- | --- |
| `qualified_offline_synthetic` | A named test module in this repository exercises this stage for this specific recipe on a synthetic host. The cell lists that module in `evidence`. |
| `implemented_unqualified` | Code and a driver for this stage and recipe exist, but the repository's own references still hold the qualification pending. Any listed `evidence` is the unqualified driver, not a result. |
| `pending` | No test in this repository exercises this stage for this recipe. Nothing is claimed. |
| `unsupported` | The declared profile excludes this combination. |
| `not_applicable` | The cell does not apply to this row, such as Node for a Python recipe. |

`qualified_offline_synthetic` does **not** establish any of the following:

- that the cited test ran or passed on a given revision or machine. Most
  installed cases skip without Linux x86-64 CPython 3.13 and an explicitly
  prepared offline wheelhouse, and the Node cases skip without the pinned
  external Node/npm and trusted TypeScript 5.8.3. Record actual interpreters,
  skips and CI runs separately;
- a real provider call, spend, canary or active exposure, or measured benefit.
  Local TLS servers, issuers and transports in these tests are synthetic;
- behavior on another host, source shape, platform, interpreter or package
  manager. Every new host needs a fresh source review and binding;
- isolation of untrusted target code, production durability or monitoring.

The `canary_active`, `provider_operation` and `measured_benefit` cells are
`pending` in every row, and the schema does not allow them to be qualified.
They need independently authenticated authority and observed evidence.

## Stages

| Stage | What a qualified cell covers |
| --- | --- |
| `source_transform` | The `implement-*` plan, baseline, apply, modified verification and owned source rollback (for JS/TS, the `js-*` equivalent). |
| `template_materialize` | Source-bound rendering of planner inputs from the versioned template catalog. |
| `entrypoint_bind` | A source-bound console or start-script binding with an owned edit. |
| `package_install` | Offline package build and hash-checked install into a private environment. |
| `supervised_launch_off` | A supervised normal installed command in runtime mode `off` with independent observation. |
| `disable` | A durable disable of that supervised session. |
| `upgrade` | A separately reviewed second installed generation selected under exact authority. |
| `rollback` | Return to the retained installed generation. |
| `connected_shadow` | An installed connected shadow session against a local synthetic protocol. |
| `connected_upgrade` | Connected generation transfer between installed generations. |
| `canary_active` | Observed canary or active exposure. |
| `provider_operation` | Real provider operation. |
| `measured_benefit` | Measured benefit from observed outcomes. |

## Matrix

`qualified` abbreviates `qualified_offline_synthetic`, `implemented`
abbreviates `implemented_unqualified` and `n/a` abbreviates `not_applicable`.
The JSON file holds the full values, evidence paths and notes.

| Row | source transform | template materialize | entrypoint bind | package install | supervised launch off | disable | upgrade | rollback | connected shadow | connected upgrade | canary active | provider operation | measured benefit | linux | windows native | node |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `python.A` | qualified | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.B` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.C` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | qualified | n/a |
| `python.D` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | pending | n/a |
| `python.E` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | pending | n/a |
| `python.F` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.G` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.H` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | pending | n/a |
| `python.I` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.J` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.K` | qualified | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | qualified | pending | n/a |
| `python.L` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | pending | n/a |
| `python.M` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | implemented | pending | pending | pending | qualified | pending | n/a |
| `javascript.recipe-c@1.0.0` | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | qualified | pending | pending | pending | pending | qualified | unsupported | qualified |

A platform cell is qualified only for the stages it lists in the JSON
`stages` field, which are always a subset of that row's own qualified stages.
A qualified platform cell therefore does not mean every stage runs there.

## How the rows were derived

- **A, B, F, G, I, J, K.** `tests/test_executable_recipes.py` and
  `tests/test_package_lifecycle.py` run the generated fixture for each letter
  through plan, verification, apply and rollback. That is the only stage
  qualified. A also has its archived example host rendered by
  `tests/test_template_catalog.py`. None has an installed host, so every
  installed, connected and platform-specific cell is `pending`.
- **C.** The generic template catalog, console binder, Linux package/install
  and delivery-session tests all use the recipe C fixture. Connected shadow is
  the independent Alpha host in `tests/test_connected_installed_binding.py`.
  This row describes the recipe; the use-case C source contract
  (`examples/coding-agent/agent.py`) is a different host and stays pending in
  the use-case matrix. Native Windows covers the listed off-mode stages
  through its own separate package, install and Job Object session APIs. It
  does not cover durable disable or the Linux package/install and delivery
  session contracts, and native Windows connected shadow is still pending
  qualification.
- **L, D, E, M, H.** Each cites only its own use-case host, bind, installed
  and connected modules. A test checks that no qualified cell here exceeds the
  corresponding field in the use-case matrix.
- **Connected shadow for M and H** is `qualified_offline_synthetic`: a local
  Linux x86-64 CPython 3.13 run with an explicit offline wheelhouse executed
  `tests/test_use_case_claim_connected.py` and
  `tests/test_use_case_retention_connected.py` with no skip, and the hosted
  3.13 leg lists both modules in `.github/required-installed-journeys.txt`,
  so a skipped case fails that job. This is a local synthetic TLS protocol
  result, not provider operation.
- **Connected upgrade for C, D, H, L, M and E** is `implemented_unqualified`:
  stopped generation transfer drivers exist, while the changelog and the
  use-case matrix keep connected upgrade pending. The L, M and E cells cite
  `tests/test_connected_generation_graph_installed.py`,
  `tests/test_connected_generation_claim_installed.py` and
  `tests/test_connected_generation_completion_installed.py`, each executed
  with no skip in a local Linux x86-64 CPython 3.13 run with an explicit
  offline wheelhouse and listed in `.github/required-installed-journeys.txt`.
  JS/TS has no transfer path and is `pending`.
- **JavaScript/TypeScript recipe C** is a separate backend with its own
  catalog entry. It supports recipe C only, on Linux x86-64 with trusted
  external Node tooling. Native Windows is `unsupported` by its manifest. It
  provides no coverage for any Python row, and no Python row provides
  coverage for it.

No two rows cite the same test module for an installed or connected stage.
One passing C host therefore cannot mark another recipe, language or platform
as supported. Promote a cell only by adding a test that exercises that stage
for that recipe, and update the data, this table and the test together.
