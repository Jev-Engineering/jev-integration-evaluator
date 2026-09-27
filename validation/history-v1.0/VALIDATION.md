# Validation report — JEV Placement Skill 1.0.0

Verified on **2026-09-26**. These checks establish that the shipped tooling executes and enforces tested contracts. They do not establish that JEV improves a real repository.

## Automated tests

**175 passed; 0 failures; 0 errors; 0 skipped.** Local test duration: 18.73 seconds. Raw output is in `pytest-output.txt`; machine-readable results are in `pytest-junit.xml` and `validation-summary.json`.

The suite covers all 13 A–M placement patterns, deterministic rejections, Python/TypeScript AST support, module-level Python code, duplicate-symbol handling, source-hash review guards, budgets and sensitive-path exclusions, unknown estimates, optimization conflicts and constrained sets, paired-data integrity, exact McNemar, clustered/Bayesian analysis, calibration semantics, actual ablation interaction, off/shadow/canary policy, bounded action validation, thresholds/activation, outages/timeouts, circuit breaking, caching, redacted hash-chain integrity, source-linked traces, test/outcome receipts, patch approval and generated adapter execution.

The package validator passed **10 schemas** and **321 synthetic run/decision records**, checked the exact-request offline replay, and confirmed the required package structure. Root and packaged schemas match. No analysis/test made a live TypeSafe request.

## End-to-end demonstrations

| Check | Result |
|---|---|
| Coding-agent, RAG, graph, deterministic service and polyglot source fixtures | Reports and machine-readable artifacts generated successfully. The combined fixtures cover A–M and NONE. |
| Deterministic-only service | Five candidates; all Tier 0; no justified integration set. |
| Offline typed runtime | One fixture response; typed `inspect` proposal; zero executed actions and zero remote requests. |
| Generated adapter | Its default-off regression test passed; manifest accurately says the arbitrary host callsite is not yet wired. |
| Paired research comparison | 80 synthetic task pairs; uncertainty, efficiency and failure transitions computed; disposition remains needs_more_evidence. |
| Router/verifier ablation | The actual difference-in-differences calculation executes, with a synthetic interaction of 0.15 and bootstrap interval. This is not measured JEV performance. |
| Budgeted placement scenario | Two placements selected from explicitly synthetic assumptions; conflicting duplicate routing is excluded; unmeasured synergy receives no bonus. |
| Source-to-outcome chain | Real generated adapter/test artifacts and a clearly synthetic outcome receipt linked to matching opportunity/source/experiment hashes. |
| Wheel build and installation | Built without index/dependency downloads, installed to an isolated directory, checked against release module bytes, then used outside the source checkout for a successful scan and schema validation. |

## Unfamiliar source-tree smoke checks

| Installed source snapshot | Files | Symbols | Candidates | Tier 0 / Tier 1 | Result |
|---|---:|---:|---:|---|---|
| click 8.1.8 | 16 | 527 | 93 | 90 / 3 | Completed read-only; no target import/test/network. |
| httpx 0.28.1 | 23 | 469 | 63 | 53 / 10 | Completed read-only; no target import/test/network. |

These checks demonstrate operation on pre-existing third-party code, not verified semantic recall/precision. Repeated declarations generated explicit disambiguation warnings. No discovered lead was automatically elevated to a strong/high-leverage recommendation, and no third-party source code is redistributed. Full fingerprints and warnings are recorded in `third-party-source-smoke.json`.

## Recorded environment

- python: `3.13.5`
- platform: `Linux`
- node: `v22.16.0`
- typescript: `5.8.3`
- pytest: `9.0.2`
- PyYAML: `6.0.3`
- jsonschema: `4.26.0`
- setuptools: `82.0.1`

The CI file defines additional interpreter checks, but this report claims only the locally executed environment above. Missing optional TypeScript tooling in another environment produces a disclosed review-only fallback.

## Explicitly untested or unperformed

No live TypeSafe/JEV call, production effectiveness study, real held-out calibration, model cost/latency measurement, user repository modification, Git push/merge or deployment was performed. Synthetic fixtures cannot supply those conclusions. Static source analysis remains a conservative architecture aid, not a whole-program proof or automatically correct insertion decision. Source-specific semantic review and authorized host wiring remain part of the skill workflow.

Reproduce local tests with `python -m pytest -q` and contract checks with `python scripts/validate_package.py`. Release maintainers can regenerate offline example evidence with `python scripts/run_release_checks.py`, which runs only generated-fixture tests and reads available third-party sources. That command intentionally rewrites release-validation artifacts; preserve any original signed/checksummed release evidence before regenerating it.

Release integrity: `SHA256SUMS` hashes the files inside the package; `scripts/build_release.py` produces a reproducible ZIP and external SHA-256 file. `python scripts/validate_package.py --check-manifest` verifies the exact listed release bytes. Hash integrity is not identity/authenticity without a trusted external digest.
