# JEV opportunity inventory

CompleteTech provider-starter

## Executive summary

Repository: **generic-service**. Files analyzed: **1**. Candidate locations: **5**. Deterministic/anti-pattern rejections: **5**. Strong or high-leverage candidates: **0**.

All unreviewed placements remain experimental. Scores are prioritization heuristics, not measured quality gains or probabilities of usefulness. Unknown cost, latency, failure rate, and task frequency are not reported as measurements.

**No JEV integration is justified by the discovered evidence.** Preserve deterministic behavior; review coverage limitations before treating this as an exhaustive negative result.

Largest risks: mislabeled boundaries, uncalibrated confidence, correlated evaluators, irreversible effects, stale evidence, and unmeasured latency/cost.

## Ranked candidate table

| Rank | ID | File / symbol | Pattern | Tier | Score [sensitivity range] | Expected benefit | Cost | Risk | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | JEV-2F28814C2216 | service.py :: exact_permission | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |
| 2 | JEV-4211FA59315A | service.py :: decode_payload | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |
| 3 | JEV-5AB575505127 | service.py :: payload_matches | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |
| 4 | JEV-6CE5FE35B530 | service.py :: total_with_tax | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |
| 5 | JEV-CCB60333437C | service.py :: order_numbers | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |

## Per-candidate evidence and design

### JEV-2F28814C2216 · deterministic_or_generative_antipattern

**Source:** `service.py::exact_permission`, lines 23–24; parser `python_ast`; source SHA-256 `89f28441e181f64e969773a9df10c2e5093adaa5032e9ab1ac2c9b3b515bfa7b`.

**Why here:** {'roles': [], 'calls': [], 'dataflow': []}. **Why JEV:** Preserve deterministic computation or an appropriate generative model. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `preferred`. Deterministic/generative anti-pattern gate; score cannot override it Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls ``; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `bypass`.

**Questions and bounded answers:**


**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** existing deterministic implementation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.000 | 0.00–0.20 | 1.6 | 0.0000 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.000 | 0.00–0.20 | 1.5 | 0.0000 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 1.000 | 0.80–1.00 | -2.4 | -0.2034 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `['Exact computation or state validation has a preferred deterministic implementation.']`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-2F28814C2216-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-4211FA59315A · deterministic_or_generative_antipattern

**Source:** `service.py::decode_payload`, lines 19–20; parser `python_ast`; source SHA-256 `a019f34c1dfeb8bf16bc11998b395a601313d25dc28192fac470b5bba2b8a7f2`.

**Why here:** {'roles': ['deterministic'], 'calls': [{'name': 'json.loads', 'resolved_name': 'json.loads', 'line': 20}], 'dataflow': []}. **Why JEV:** Preserve deterministic computation or an appropriate generative model. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `preferred`. Deterministic/generative anti-pattern gate; score cannot override it Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `json.loads`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `bypass`.

**Questions and bounded answers:**


**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** existing deterministic implementation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.000 | 0.00–0.20 | 1.6 | 0.0000 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.000 | 0.00–0.20 | 1.5 | 0.0000 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 1.000 | 0.80–1.00 | -2.4 | -0.2034 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `['Exact computation or state validation has a preferred deterministic implementation.']`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-4211FA59315A-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-5AB575505127 · deterministic_or_generative_antipattern

**Source:** `service.py::payload_matches`, lines 15–16; parser `python_ast`; source SHA-256 `657c7659d4b061d3b2cd9d003ce85302f5919629200169f1190ef277cd2f1835`.

**Why here:** {'roles': ['deterministic'], 'calls': [{'name': 'hmac.compare_digest', 'resolved_name': 'hmac.compare_digest', 'line': 16}, {'name': 'hashlib.sha256().hexdigest', 'resolved_name': 'hashlib.sha256().hexdigest', 'line': 16}, {'name': 'hashlib.sha256', 'resolved_name': 'hashlib.sha256', 'line': 16}], 'dataflow': []}. **Why JEV:** Preserve deterministic computation or an appropriate generative model. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `preferred`. Deterministic/generative anti-pattern gate; score cannot override it Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `hmac.compare_digest, hashlib.sha256().hexdigest, hashlib.sha256`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `bypass`.

**Questions and bounded answers:**


**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** existing deterministic implementation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.000 | 0.00–0.20 | 1.6 | 0.0000 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.000 | 0.00–0.20 | 1.5 | 0.0000 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 1.000 | 0.80–1.00 | -2.4 | -0.2034 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `['Exact computation or state validation has a preferred deterministic implementation.']`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-5AB575505127-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-6CE5FE35B530 · deterministic_or_generative_antipattern

**Source:** `service.py::total_with_tax`, lines 7–8; parser `python_ast`; source SHA-256 `ad5ca8603f67002862264e334ff0cc93e17fa85145a81814b0c1906a6c0b29e6`.

**Why here:** {'roles': ['deterministic'], 'calls': [{'name': 'round', 'resolved_name': 'round', 'line': 8}], 'dataflow': []}. **Why JEV:** Preserve deterministic computation or an appropriate generative model. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `preferred`. Deterministic/generative anti-pattern gate; score cannot override it Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `round`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `bypass`.

**Questions and bounded answers:**


**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** existing deterministic implementation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.000 | 0.00–0.20 | 1.6 | 0.0000 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.000 | 0.00–0.20 | 1.5 | 0.0000 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 1.000 | 0.80–1.00 | -2.4 | -0.2034 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `['Exact computation or state validation has a preferred deterministic implementation.']`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-6CE5FE35B530-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-CCB60333437C · deterministic_or_generative_antipattern

**Source:** `service.py::order_numbers`, lines 11–12; parser `python_ast`; source SHA-256 `a64c06f1e180f6c5fdfeeea9e933fc6e4a4c0fa710e4a102cbc0ed98bed53399`.

**Why here:** {'roles': ['deterministic'], 'calls': [{'name': 'sorted', 'resolved_name': 'sorted', 'line': 12}], 'dataflow': []}. **Why JEV:** Preserve deterministic computation or an appropriate generative model. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `preferred`. Deterministic/generative anti-pattern gate; score cannot override it Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `sorted`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `bypass`.

**Questions and bounded answers:**


**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** existing deterministic implementation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.000 | 0.00–0.20 | 1.6 | 0.0000 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.000 | 0.00–0.20 | 1.5 | 0.0000 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 1.000 | 0.80–1.00 | -2.4 | -0.2034 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `['Exact computation or state validation has a preferred deterministic implementation.']`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-CCB60333437C-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

## Coverage and unknowns

```json
{
  "languages": {
    "python": 1
  },
  "files_analyzed": 1,
  "files_considered": 2,
  "symbols": 6,
  "truncated": false,
  "parser_counts": {
    "python_ast": 1
  },
  "ignored": [],
  "warnings": [],
  "limitations": [
    "Call edges are conservative static approximations, not a complete dynamic call graph.",
    "Python and JavaScript/TypeScript use ASTs when available; all other languages require agent-led source review.",
    "Unknown dynamic dispatch, reflection, macro expansion, framework callbacks, and deployment effects need traces or review.",
    "Tests and dependency sightings indicate availability, not correctness or installed versions."
  ]
}
```
