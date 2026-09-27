# Validation report — JEV Placement Skill 1.2.0

Verified on **2026-09-26** against the actual supplied v1.1.0 ZIP. These checks establish that the packaged software executes and enforces its tested contracts. They do not establish that JEV improves a real application.

## Automated regression and new tests

**459 tests passed; 0 failures; 0 errors; 0 skipped.** The full-suite run completed in 24.20 seconds in the recorded local environment. Raw output is in `pytest-output.txt`, machine-readable results in `pytest-junit.xml`, and the release summary in `validation-summary.json`.

The unmodified v1.1.0 package first passed its 296-test baseline. This release adds **163 tests**, and all **14 original test files remain byte-for-byte unchanged**. Input archive identity, added/modified files, and preservation checks are in `upgrade-provenance.json`; baseline output is in `baseline-v1.1-pytest.txt`.

| Area | Executed checks |
|---|---|
| Shared budgets and runtime | Concurrent atomic admission, call/cost limits across routers, nonrefundable failures, exactly-once settlement, overrun suspension, closed tasks, registry capacity, bounded in-flight requests, shadow admission, cache reuse without new reservations, request-copy isolation, audit failures and exact-runtime approval changes. |
| Scenario optimization | Nominal versus worst-case choices; all resource constraints across scenarios; source/semantic rejection; prerequisites, cycles and conflicts; unmeasured synergy; explicit no-integration results; invalid/missing values; beam disclosure; 12 randomized small problems checked against an independently enumerated oracle and monotonic budget relaxation. |
| Every-gate studies | Complete matching gate sets and raw holdouts; report/plan/model/policy/source/question-role binding; omitted/altered evidence; alpha allocation; task/cluster leakage; full downstream denominators; missing bundles; synthetic-evidence blocks and independently pinned study requirements. |
| Canary operational windows | Complete schedules and stable arm assignment, per-cohort minimums, missing outcomes, unknown metrics, preserved safety incidents, absolute/comparative limits, full action-count coverage, unknown-label drift, zero-action evidence, stale/open windows, provenance/time errors and scope-bound suspend-only host controls. |
| CLI and accounting | A complete 17-command offline v1.2 workflow; enforcement exit statuses; readable sidecars; repeated-output protection; no new inference tokens counted on cache hits. |
| Original capabilities | All original scanner, scoring, optimizer, paired statistics, calibration, robustness, lifecycle, runtime, implementation, patch, tracing, onboarding and schema/packaging tests still pass. |

Some unit tests explicitly use fabricated records marked `observed` solely to exercise branches requiring that input classification. They are clearly documented test fixtures, not observed JEV research, independently issued approvals, or production evidence.

## Package contracts

The validator passed **22 JSON schemas** and **321 existing synthetic run/decision records**. It also checked the new scenario/monitor/activation templates, release-version consistency, required package structure, matching source and installed-package schema copies, and exact local replay fixtures. See `package-validation.json`.

The six added schemas cover scenario specifications, deployment gates, complete gate bundles, monitoring specifications, frozen monitoring plans and monitoring outcomes. The study/run/activation contracts retain compatible inputs while adding the v1.2 fields.

## End-to-end demonstrations

| Check | Executed result |
|---|---|
| Original source fixtures | Coding-agent, RAG, graph, deterministic service and polyglot fixtures produced current reports and machine-readable artifacts. A–M plus `NONE` remained represented across the fixtures. |
| Deterministic-only fixture | Five rejected Tier 0 candidates; no justification for introducing JEV. |
| Generated adapter | Its generated default-off regression test passed. The factory requires expiring and exact-runtime-bound receipts; no host callsite wiring or deployment is claimed. |
| Original runtime and research examples | Offline runtime, paired comparison, calibration, replay, ablation, economics and source-to-artifact links ran successfully with explicitly synthetic outcomes. |
| v1.1 compatibility workflow | **19 CLI operations** completed, including rescan/diff, frozen study/holdout checks, five robustness probes and audit checkpoints. |
| v1.2 every-gate workflow | **17 CLI operations** completed; two synthetic gates, 80 calibration observations, 240 held-out observations, and 80 paired task outcomes. Both numerical gate checks passed, but adoption remained `needs_more_evidence` because the evidence is synthetic. |
| v1.2 shared runtime budget | Three shadow submissions across two routers admitted only two fixture calls. All returned proposals remained baseline-controlled; zero host actions and zero remote requests. |
| v1.2 monitoring | An 80-task schedule exercised a complete synthetic window, a known incident and an incomplete overdue window. Synthetic healthy evidence failed enforcement; incident/overdue reports recommended suspension without invoking any host action. |

Evidence is stored under `lifecycle-v11/`, `lifecycle-v12/`, `examples/`, `offline-runtime/`, and their companion output logs. Demonstrations use fabricated data to exercise software, not to estimate model performance. The optional host suspension hook is exercised with artificial unit-test router objects, not a real deployment.

## Unfamiliar installed source trees

| Read-only source snapshot | Files analyzed | Symbols | Candidates | Tier 0 / Tier 1 |
|---|---:|---:|---:|---:|
| Click 8.1.8 | 16 | 527 | 93 | 90 / 3 |
| HTTPX 0.28.1 | 23 | 469 | 63 | 53 / 10 |

Both scans completed without source-coverage truncation. Duplicate declarations generated explicit disambiguation warnings. No third-party target module/test was executed and no original third-party source was copied into this package. These are operational source-reader smoke tests, not validated semantic recall or precision. See `third-party-source-smoke.json`.

## Installed-wheel verification

The v1.2.0 wheel was built with dependency/index access disabled, installed to an isolated target directory, and exercised from a directory outside the checkout. Eight CLI operations verified the version, deterministic scan, robust selection, every-gate study, monitoring enforcement and new schemas. **53 installed Python/data/parser files matched the release module bytes.** See `wheel-build.txt`, `wheel-install.txt`, and `wheel-smoke.json`.

The wheel is a Python toolkit distribution. The complete ZIP additionally contains the agent skill, documentation, scripts, templates, examples and tests. No new external runtime dependency was introduced.

## Recorded environment and unexecuted environments

Python 3.13.5; Linux x86_64; pytest 9.0.2; PyYAML 6.0.3; jsonschema 4.26.0; setuptools 82.0.1; Node v22.16.0; TypeScript 5.8.3. Exact strings are in `environment.json`.

The configured CI matrix includes other Python interpreters, but this report claims only the interpreter/platform actually run here. Windows/macOS execution, distributed budgeting, live network behavior and production integrations were not validated in this release construction.

## Release integrity and historical evidence

The release builder writes `SHA256SUMS` for the exact included file set, then creates a deterministic ZIP and external SHA-256 checksum. `python scripts/validate_package.py --check-manifest` verifies the listed bytes and rejects additions, missing files, duplicate entries and unsafe paths. A locally regenerated manifest is not independent verification; retain a trusted external digest or signature for authenticity.

Earlier v1.1 records are preserved under `history-v1.1/`, and earlier v1.0 history remains under `history-v1.0/`. They are explicitly historical and do not supply this release's current test counts or measured claims. The original ZIP remains authoritative for each earlier release.

## Explicit limitations

No live JEV request, real effectiveness study, production calibration, user-repository execution/modification, Git publication or deployment was performed. Scenario assumptions are not confidence intervals; additive resource estimates are not an end-to-end queueing or risk model. Beam search is not proven optimal. Shared budgets are process-local and require deliberate host scope management. Gate hashes cannot authenticate labels, independence or untouched holdouts. Monitoring metrics are descriptive operational guards, not sequential significance or causal estimates. Receipts and suspension cannot replace host execution-time authorization or undo already executed actions.

## Reproduce

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/validate_package.py
python scripts/run_v11_demo.py --out ../fresh-v11-demo
python scripts/run_v12_demo.py --out ../fresh-v12-demo
```

Only install dependencies after approving that environment change. Demo output directories must be new or empty. `scripts/run_release_checks.py` intentionally regenerates current validation examples; preserve the original archive/digest before regenerating release evidence.
