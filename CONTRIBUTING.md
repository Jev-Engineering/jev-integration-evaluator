# Contributing

Use a scoped branch or worktree. Add a regression test for each bug, keep package/root schemas identical, update data-contract examples when changing a schema, and preserve source-hash version guards. Do not add network calls to ordinary tests.

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/validate_package.py
```

Test Python-only mode and TypeScript-enabled mode. A missing optional parser must remain an explicitly disclosed fallback, not a crash or silently verified result. Synthetic data must retain its evidence label and cannot be promoted to an observed outcome.

For independent path qualification, run
`python -m pytest -q tests/test_path_corpus_connected.py tests/test_path_corpus_oracle.py tests/test_path_corpus_mutations.py`
and `python tests/path_corpus/generate_support.py --out NEW_JSON` on Linux.
Compare the generated JSON with `validation/path-corpus-support-v1.json` after
reviewing changes to both host source and oracle. Keep unrun paths explicit;
the trusted-host synthetic verifier does not qualify installed startup.

For the bounded JS/TS backend, use native POSIX with trusted Node and pinned
TypeScript 5.8.3 outside the target. Run `python -m pytest -q
tests/test_js_lifecycle.py tests/test_js_backend_trusted.py tests/test_js_entrypoint.py tests/test_js_template_delivery.py`
and `node --test tests/js_transform.test.cjs tests/native_js_runtime.test.cjs`.
Also run the installed-wheel lifecycle test, full suite, package validation
and offline demos. Record exact Node/compiler identities and unsupported A–M
recipes; never load target plugins or compiler configuration during planning.

Keep configuration strict, stable CLI errors actionable, archives free of credentials/build caches, and citations to primary upstream API documentation dated. Changes to confidence semantics, threshold activation, budgets, authorization, cache keys, paired matching and statistical assumptions require focused tests and a version note. Re-generate release checksums only after tests and documentation are final.

For executable-integration changes, also run `python scripts/run_implementation_demo.py --out NEW_PRIVATE_DIRECTORY` and the installed-wheel host test. Keep the support matrix and all strict implementation schema copies current. Do not publish private target bundles. Record actual interpreters/platforms; unrun CI jobs and live activation are not local validation results.

For template catalog changes, keep the packaged manifest, mirrored request/manifest/lock schemas, CLI/API, lifecycle matrix, references and wheel checks aligned. Run `tests/test_template_catalog.py` and `tests/test_template_materialization_wheel.py`, then rebuild `SHA256SUMS` after final edits and run `python scripts/validate_package.py --check-manifest`. Template materialization is an offline planner-input gate, not installed host delivery.

For template installation changes, keep the five mirrored package/install
schemas, CLI/API, Linux profile, recovery journal, reference and clean-host
test aligned. Ordinary tests never acquire packages. When explicitly scoped,
prepare a private wheelhouse with
`python scripts/prepare_template_wheelhouse.py --out NEW_EXTERNAL_DIRECTORY`
and set `JEV_TEMPLATE_WHEELHOUSE` before running
`tests/test_template_installation.py` on Linux x86-64 CPython 3.13. The hosted
3.13 job prepares this wheelhouse before the test suite. Record the wheelhouse
source, interpreter, skips and exact failure stage. Rebuild checksums after
the final edit.

Optionally, after a run that wrote `--junitxml`, summarize the registered-tool
template gates with
`python scripts/run_registered_tool_qualification.py --junit JUNIT_XML --out NEW_EXTERNAL_JSON`.
This report step is not a required check. It runs no test or target, lists
failed and unrun gates explicitly, and always leaves provider operation, canary,
active and measured benefit pending. Keep its gate list, the
[quickstart](references/registered-tool-template-quickstart-v1.md) support matrix
and both report schema copies aligned.

The six installed generated-adapter console tests also accept that explicit
offline wheelhouse (`JEV_WINDOWS_TEMPLATE_WHEELHOUSE` for native Windows).
They then install the newly built evaluator/host wheels and declared runtime
dependencies into a child venv with system site disabled, and check import
origins there. Without this opt-in input, their existing system-site test
profile remains available. Installing dependencies in a parent test venv does
not make them available in a child's base-interpreter system site.

For dev3 changes, retain the observation-contract, full-schedule receipt, unavailable-command, real process-termination and source-fidelity regressions. Re-verification after interruption must not reuse a historical pass as current evidence.

For discovery changes, run all `tests/test_capabilities*.py` suites on a supported
POSIX filesystem, including the installed-wheel CLI check. Retain the native
unsupported-platform result, redacted failures, exclusive external outputs,
source/policy/parser identity guards and mandatory eligibility exclusions.
Historical examples bind their recorded parser; regenerate fresh anchors for a
different interpreter or repository. Also run the nomination-inventory, repository
discovery CLI and installed-wheel suites, plus `scripts/run_capability_demo.py`
with a new external private directory. Bind bridge engine identity and all
source/policy restrictions; semantic review cannot override eligibility or
provide measured estimates, bindings or authority. Keep issue #5 open until its
complete source-reviewed no-useful-placement acceptance criterion is delivered.

For review-gate changes, run `tests/test_review_gate_invariants.py` and current
traceability/scoring callers. A failed batch must leave the input inventory intact;
success must preserve existing candidate references. Rebuild source-linked bridge
examples when scoring or bridge code changes, because engine hashes invalidate old
preparations. Keep issue #7 open until its full selection contract is delivered.


For the finite independent-package owner or dual generation path, keep public
CLI/API, genuine owner contracts and both schema copies aligned. Run
`tests/test_connected_packages_installed.py` and
`tests/test_connected_generation_dual_installed.py` on explicitly scoped Linux
x86-64 CPython 3.13 with the prepared offline wheelhouse. Both modules are in the
hosted required installed-case list; skipped or missing cases fail that gate.
Stabilize code, schemas, packaged references and documentation before building
any qualification wheel, then freeze them through the complete installed run.
Retain failed runs separately. Entry-point claims in shadow mode describe actual
source-owned invocations, not treatment registry effects or provider benefit.
