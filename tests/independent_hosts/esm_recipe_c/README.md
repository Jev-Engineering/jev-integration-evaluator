# Independent ESM recipe C host

This finite Linux Node fixture is existing ESM application source, separate from
the evaluator and the CommonJS/TypeScript fixtures. `package.json` declares the
normal `node start.mjs` command. That command imports `seam` from `host.mjs`,
requires `JEV_RUNTIME_MODE=off`, and invokes the reviewed `read` action. The
host's `original` function writes the raw effect through its callback before
the entrypoint writes independent ready and integration files. The default
policy has one legal action and retains host permission validation.

`review-v1.json` pins every package source file for versions 1.0.0 and 1.0.1
before copy, scanning or materialization. Version 1.0.1 changes the actual
`host.mjs` return and effect argument to append `:v2`; the source and normal
command changes are separately reviewed. The strict review schema is mirrored
in `schemas/` and packaged evaluator data.

On Linux x86-64 with pinned Node 24.18.0, npm 11.16.0, and a separately
reviewed TypeScript 5.8.3 package outside the target, run the focused test:

```bash
PATH=/absolute/pinned/node/bin:$PATH \
JEV_TRUSTED_TYPESCRIPT_PACKAGE=/absolute/trusted/typescript \
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/offline-wheelhouse \
python3.13 -m pytest -q tests/test_node_template_installed_esm.py
```

The test copies the trusted compiler into private tooling, checks complete
tool and source-tree digests, builds and installs an evaluator wheel, and
materializes the pinned ESM request through the installed CLI with no checkout
import. It then uses the existing JS plan/baseline/apply/modified receipt path,
offline npm package/install APIs, Node descriptor and exact-scope supervisor.
The first installed command yields `read:alpha`, the upgraded source yields
`read:beta:v2`, and each has a separate ready/integration observation. It
checks installed command and entrypoint origins, source and toolchain drift
refusal, a safe interrupted launch before child release, disable, retained
generation selection rollback and owned source rollback. Old observation paths
are consumed and cannot be replayed after rollback. Both installed generations
and historical effects remain for review.

This is synthetic offline host evidence. It does not qualify provider contact,
connected modes, production migration, distributed budgets, measured benefit,
arbitrary ESM syntax, target compiler configuration, or npm lifecycle hooks.
