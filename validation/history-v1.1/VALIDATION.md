# Validation report — JEV Placement Skill 1.1.0

Verified on **2026-09-26** against the packaged local implementation. These tests validate contracts and execution paths, not live JEV effectiveness.

## Automated suite

**296 passed; 0 failures; 0 errors; 0 skipped.** This includes the 175-test original suite and **121 additional tests**. The final run recorded approximately 21.82 seconds. Raw output: `pytest-output.txt`; machine-readable evidence: `pytest-junit.xml` and `validation-summary.json`.

| Area | Verified checks |
|---|---|
| Existing placement workflow | A–M patterns, deterministic rejections, native Python/TypeScript analysis, scoring/optimization, runtime fallbacks, paired statistics, authorized patching and generated adapters still pass. |
| Snapshot lifecycle | Configuration-only and settings-only changes affect identity; body changes and line shifts are distinguished; legacy/partial coverage does not prove removal; candidate identity collisions are rejected; configured Git fsmonitor is not invoked. |
| Frozen studies | Entire scheduled denominator is required, including omissions from both arms; version/split/task/seed checks; failure/timeout handling; fixed analysis settings; exact holdout/rubric linkage; decision-label accuracy cannot justify downstream adoption. |
| Held-out risk | Split leakage, missing observations, repeated clusters, changed provenance, subgroup insufficiency, stricter thresholds, numerical consistency and synthetic-only activation rejection. |
| Rubric probes | Label-order identity, normalized label remapping, changed-meaning rejection, invalid/missing response accounting, explicit budgets, redacted failures and insertion-order HTTP serialization with a mocked transport. |
| Runtime lifecycle | Per-action floors cannot weaken defaults; strict expiry/issue/order/evidence bindings; revocation; in-flight suspension/expiry; immutable receipt copy; order-sensitive cache; audit truncation detection. |
| Release integrity | Exact manifest passes; unlisted additions, duplicate entries and parent traversal are rejected in isolated package copies. |
| CLI | Nineteen offline operations execute end to end; human-readable sidecars exist; synthetic enforcement exit 3 is asserted; source inputs are not silently overwritten. |

## Contracts and numerical cross-check

The package validator passed **16 schemas** (six new) and **321 original synthetic run/decision records**, verified the duplicated packaged schemas and checked the new example input templates. Exact offline replay remains executable.

The new one-sided binomial upper-limit calculation was compared with locally installed **SciPy 1.17.0** on **80 combinations** of counts, errors and alpha. Maximum absolute difference was **4.937e-13**. Full inputs/results are in `binomial-crosscheck.json`. SciPy was used only as an independent local numerical reference; no SciPy runtime dependency was added. Matching arithmetic does not establish independent sampling, label truth or predictive effectiveness.

## Offline end-to-end evidence

`lifecycle-v11/` contains generated source snapshots, structured inputs, frozen manifests and human/machine-readable reports. The demo performed **19 CLI operations**, using **80 synthetic paired tasks**, **40 synthetic calibration observations**, **120 synthetic holdout observations**, **five fixture-backed robustness probes**, and a **three-event audit checkpoint**. All numerical examples are fabricated test evidence. The study remains `needs_more_evidence`; synthetic holdout activation eligibility remains false and enforcement returns 3.

The original coding-agent, RAG, graph, deterministic-service and polyglot examples were regenerated with v1.1. The deterministic service again produced five Tier 0 candidates and no justified integration set. The generated adapter's default-off test passed and its factory now selects strict expiring activation. No arbitrary host callsite was wired.

Read-only scans of the locally installed Click and HTTPX source trees were repeated. Their fingerprints, coverage, versions and warnings are recorded in `third-party-source-smoke.json`. These are unfamiliar-repository smoke checks, not validated detector precision/recall. No third-party source is redistributed.

## Distribution test

A wheel was built using `--no-deps --no-build-isolation --no-index`, installed to an isolated target directory, and exercised from outside the source checkout. Package module bytes matched the source and all 16 schemas were present. An installed-wheel scan rejected all five deterministic-service candidates; new study, schema, threshold and robustness commands also passed their expected gates. Evidence: `wheel-smoke.json`, `wheel-build.txt`, and `wheel-install.txt`.

The ZIP builder generates reproducible archives for unchanged input bytes. `SHA256SUMS` covers the exact included package file set, and an external ZIP SHA-256 is supplied. `python scripts/validate_package.py --check-manifest` verifies those bytes and rejects unlisted changes. A locally regenerated digest is not a trusted signature or proof of authorship.

## Environment

| Component | Executed version |
|---|---|
| python | `3.13.5` |
| platform | `Linux-6.18.44-x86_64-with-glibc2.41` |
| pytest | `9.0.2` |
| PyYAML | `6.0.3` |
| jsonschema | `4.26.0` |
| setuptools | `82.0.1` |
| scipy | `1.17.0` |
| node | `v22.16.0` |
| typescript | `5.8.3` |

Only this local environment was executed here. The CI matrix describes additional interpreters but is not evidence that remote CI or Windows validation ran.

## Explicitly not performed

No live TypeSafe/JEV request, production calibration, field-effectiveness benchmark, latency/price measurement, user repository modification, Git push/merge or deployment was performed. Unit tests using an `observed` flag are explicitly artificial fixtures testing the observed-only branch, not actual observational studies.

Fresh rescans are not incremental parsing. Static dependencies remain incomplete. Exact bound assumptions, holdout reuse restrictions and distribution-shift limitations are documented in `references/lifecycle-and-evidence.md`. Five probes on one state do not certify robustness. Expiring receipts are unauthenticated host assertions; deterministic policy still owns execution authority. A suspended router cannot cancel already transmitted network requests or undo previously returned proposals.

`history-v1.0/` preserves selected original validation records; it is historical evidence, not the current report. The original v1.0 ZIP is unchanged.

## Reproduce

```bash
python -m pytest -q
python scripts/validate_package.py
python scripts/run_v11_demo.py --out ../new-empty-v11-demo
python scripts/validate_package.py --check-manifest
```

The demo writes only its requested new/empty output directory and a temporary synthetic source fixture. The original release-check runner intentionally regenerates known validation artifacts; preserve release evidence before using that maintainer command.
