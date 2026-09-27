# Primary-source verification record

Verified for package construction on **2026-09-26**. These references inform the adapter and methodological distinctions; they do not establish that JEV improves any example or user repository. Recheck moving API/model/compiler contracts before a live release. No provider performance claim or live benchmark result was imported into the opportunity scores.

| Primary source | Used for |
|---|---|
| https://docs.typesafe.ai/api | `/v1/systemone` request/response structure, Choice/Noul/Score descriptors, finite label distributions and usage metadata. |
| https://docs.typesafe.ai/confidence | Distinguishing distribution-derived provider confidence, answer probabilities and Noul semantics. |
| https://docs.typesafe.ai/models | The explicitly pinned `jev-1.13.0` model identifier; aliases and published limits/prices may move. |
| https://docs.typesafe.ai/sdk/python | Cross-checking supported question primitives and intended SDK semantics. The shipped minimal adapter uses HTTP, not an uninstalled SDK. |
| https://docs.typesafe.ai/patterns/fan-out | Common-state independent-question batching; no assumed automatic cross-question reasoning or unlimited batching. |
| https://docs.typesafe.ai/model-jaggedness/jev-1.13 | Motivation for explicit evidence, bounded decisions, deterministic precision and avoiding unjustified numeric/generalization claims. |
| https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API | Read-only TypeScript source parsing through the compiler API and the need to guard major-version interface changes. |
| https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html | Cross-checking paired resampling/interval distinctions. The implementation is standard-library percentile/cluster bootstrap, not SciPy BCa. |
| https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html | Cross-checking exact paired binary testing. The package implements the conditional-binomial calculation directly. |

The request validator permits 2–255 Choice labels and 2–10 Score levels. Its 255-question batch ceiling and 96,000-byte request ceiling are conservative **application policies**, not claims of the provider's complete question-count or tokenizer limits. Do not infer a fixed “65,535 combinations” capability from these values. Question IDs are for response association; each rubric must contain its own complete semantics.

Prices remain null in default configuration even though the provider publishes prices. Operators must record the currently verified price and chosen units before computing live cost. No charge-free assumption is made for failed, late or cached-original requests.

The original supplied objective/47 sections are preserved verbatim in `requirements-source.txt`. Its requirements—not the external sources—define this skill's requested deliverables. Source/code behavior, measured trace evidence and external contract facts remain distinguishable in reports.

## Additional v1.1 verification — 2026-09-26

| Primary source | Role in this release |
|---|---|
| https://docs.typesafe.ai/confidence | Risk-dependent action thresholds and the distinction between provider confidence and label probabilities. |
| https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery | Motivation for separated development/holdout data and explicit question screening; its task-specific reported results are not imported here. |
| https://arxiv.org/abs/2609.26758 | *Type-Safe Is Not Error-Free: A Constrained Decision Head Follows the Option Name, Not the Rubric Bound to It*, revised September 23, 2026. Motivation for testing label-binding sensitivity, not proof of failure in this package or every JEV application. |
| https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html | Exact Clopper–Pearson interval reference. The package computes a one-sided error upper limit directly, without a SciPy runtime dependency. |

Implementation choices (five probes, complete schedules, frozen bindings, stricter runtime factories) are authored design decisions. External research motivates checks; the shipped synthetic fixtures only validate tool behavior. The numerical cross-check uses the locally available SciPy version recorded in `validation/binomial-crosscheck.json`, which need not be the documentation site's current version.

## v1.2 implementation references — checked 2026-09-26

- Python official threading documentation: https://docs.python.org/3/library/threading.html . Used for the scope of locks/bounded semaphores and the explicit limitation that threads are not forcibly stopped by the runtime's timeout or suspension controls. This release introduces no new threading dependency.
- TypeSafe official confidence documentation: https://docs.typesafe.ai/confidence . Probability distributions and provider confidence remain separate quantities; the existing model pin/API contract is unchanged. No provider price, calibration guarantee or live effectiveness result was inferred from these docs.

Scenario objectives and monitoring summaries are implemented/disclosed engineering calculations, not imported effectiveness claims. A total-variation action comparison is descriptive, and no sequential-testing guarantee is asserted. The new all-gate alpha allocation is a union-bound budget over the existing exact per-gate/subgroup checks; it cannot establish authenticity, independence, representativeness or downstream joint utility.
