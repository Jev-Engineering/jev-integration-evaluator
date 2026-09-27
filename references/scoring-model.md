# Transparent placement scoring

The 16 dimensions are normalized to [0,1]. Default weights deliberately differ:

| Dimension | Weight |
|---|---:|
| `semantic_uncertainty` | +1.60 |
| `decision_boundedness` | +1.50 |
| `downstream_consequence` | +1.60 |
| `decision_frequency` | +0.50 |
| `cost_of_wrong_decision` | +1.20 |
| `recoverability_value` | +1.00 |
| `observability` | +0.50 |
| `deterministic_alternative_quality` | -2.40 |
| `current_failure_rate` | +0.90 |
| `current_llm_dependency` | +0.80 |
| `latency_sensitivity` | -1.20 |
| `cost_sensitivity` | -0.70 |
| `implementation_complexity` | -0.80 |
| `testability` | +1.00 |
| `expected_reuse` | +0.50 |
| `confidence_calibration_value` | +0.70 |

The implemented formula is `clip(sum(weight × dimension) / sum(positive weights), 0, 1)`. These are prioritization preferences, not learned causal coefficients or probabilities. Negative dimensions penalize model use. Configure them in `jev-config.yaml`; weights may become zero but may not reverse a dimension's meaning. At least one positive weight must remain.

Every dimension stores value, lower/upper sensitivity bounds, observed/inferred/unknown status, rationale and evidence references. Unknown dimensions use a neutral display midpoint 0.5 with [0,1] bounds; this midpoint is **not a measurement**. Missing numeric resource estimates remain null and block optimization admission. The composite interval propagates each bound with its weight's sign and clips to [0,1]. It is a sensitivity envelope, never a confidence interval.

Default threshold cutoffs are 0.55 for a strong candidate and 0.75 for high leverage, but evidence gates precede thresholds. **Tier 0:** deterministic/generative/hard-real-time rejection. **Tier 1:** unreviewed or still experimental. **Tier 2:** source-hash-matched semantic review and sufficient score. **Tier 3:** reviewed high score plus at least 30 source-matched runtime observations explicitly classified observed rather than synthetic. Thirty events are only an evidence-presence gate; they do not prove usefulness, independence or sufficient power. Every tier remains `deployment_status: not_validated` until a separately reviewed experiment.

A review must identify the reviewer, exact source SHA-256 and reasoning about the real semantic boundary. It may supply fully explained dimension values and estimate provenance. Source changes invalidate a stale review. Candidate IDs derive from relative file, qualified symbol and pattern rather than line number; repeated declarations are disambiguated by declaration order and explicitly warned about.

Use downstream fan-out, reachable nodes and a dependency-depth lower bound to find possible leverage, not to infer a causal effect. Static fan-out is not observed call frequency. Traces supply frequency, latency, failure and repeated-state observations only when source file/symbol/hash match exactly. Do not count a confidence decision as an outcome label or mistake correlation for the cause of a downstream failure.
