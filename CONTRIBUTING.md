# Contributing

Use a scoped branch or worktree. Add a regression test for each bug, keep package/root schemas identical, update data-contract examples when changing a schema, and preserve source-hash version guards. Do not add network calls to ordinary tests.

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/validate_package.py
```

Test Python-only mode and TypeScript-enabled mode. A missing optional parser must remain an explicitly disclosed fallback, not a crash or silently verified result. Synthetic data must retain its evidence label and cannot be promoted to an observed outcome.

Keep configuration strict, stable CLI errors actionable, archives free of credentials/build caches, and citations to primary upstream API documentation dated. Changes to confidence semantics, threshold activation, budgets, authorization, cache keys, paired matching and statistical assumptions require focused tests and a version note. Re-generate release checksums only after tests and documentation are final.

For executable-integration changes, also run `python scripts/run_implementation_demo.py --out NEW_PRIVATE_DIRECTORY` and the installed-wheel host test. Keep the support matrix and all strict implementation schema copies current. Do not publish private target bundles. Record actual interpreters/platforms; unrun CI jobs and live activation are not local validation results.

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
