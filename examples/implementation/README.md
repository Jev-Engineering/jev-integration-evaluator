# Source-matched synthetic implementation examples

Each `a`–`m` directory has an **unmodified synthetic target**, a real scanner/review inventory, and a strict `binding.example.json`. These examples contain no final replacement source and require no live key. The generator is `scripts/implementation_fixtures.py`; the end-to-end CLI demonstration is `scripts/run_implementation_demo.py`.

Do not apply an example to a different source by merely changing its hashes. Copy the target into a new workspace, scan/review that actual source and regenerate its binding identities. The demo does this automatically and restores every target before exiting. It distinguishes synthetic changed decisions, actual host-wiring evidence, and the absence of any deployment/benefit claim.

Host callback contracts, supported shapes, permissions and the exact command sequence are documented in `references/executable-integrations.md`. The fixture's runtime callback is intentionally supplied by the separately authorized probe; it is not a production provider bootstrap implementation. Unanchored status remains applied-but-unverified until an independently trusted receipt digest is supplied.

For a regular `src/pkg/host.py` source, the package contract is `"package_binding":{"version":"1.0","namespace":false,"module":"pkg.host"}`. The owned adapter path is `src/pkg/<output.module>.py`, and both that path and `src/pkg/host.py` must appear in `output.permitted_edits`. A namespace package uses `namespace:true` only after explicitly reviewing the missing initializer path. The planner records hashes for the selected module, package initializers and any statically imported binding modules. These synthetic layouts are exercised by `tests/test_package_lifecycle.py` and the installed-wheel test.

`observation.example.json` is a synthetic baseline probe observation for contract illustration. It is not a receipt, does not authenticate execution and cannot authorize apply or activation. Validate it with `validate --kind implementation-observation`; verification also checks trace roles and arity against the bound recipe.
