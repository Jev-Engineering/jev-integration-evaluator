# JEV opportunity inventory

CompleteTech provider-starter

## Executive summary

Repository: **graph-system**. Files analyzed: **1**. Candidate locations: **3**. Deterministic/anti-pattern rejections: **0**. Strong or high-leverage candidates: **0**.

All unreviewed placements remain experimental. Scores are prioritization heuristics, not measured quality gains or probabilities of usefulness. Unknown cost, latency, failure rate, and task frequency are not reported as measurements.

First experiment to review: **JEV-91A74DABC9DB** at `entities.py::reconcile`. Validate the proposed boundary, record a baseline, and use offline/shadow evaluation first.

Largest risks: mislabeled boundaries, uncalibrated confidence, correlated evaluators, irreversible effects, stale evidence, and unmeasured latency/cost.

## Ranked candidate table

| Rank | ID | File / symbol | Pattern | Tier | Score [sensitivity range] | Expected benefit | Cost | Risk | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | JEV-91A74DABC9DB | entities.py :: reconcile | L | 1 | 0.554 [0.167, 0.908] | Test reduced false merges while retaining provenance and reversible mutations. | unknown | unknown | unknown | experimental |
| 2 | JEV-B5DC8157D3F1 | entities.py :: reconcile | B | 1 | 0.533 [0.146, 0.892] | Test whether semantic scope assessment catches unintended side effects before deterministic policy. | unknown | unknown | unknown | experimental |
| 3 | JEV-F8BA17EB6536 | entities.py :: reconcile | M | 1 | 0.533 [0.146, 0.892] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |

## Per-candidate evidence and design

### JEV-91A74DABC9DB · graph_entity_mutation

**Source:** `entities.py::reconcile`, lines 2–7; parser `python_ast`; source SHA-256 `85f8600662bd618ae47cc88401d8c77a926361e2bd3c039d09ea48cb37d408f3`.

**Why here:** {'roles': ['graph', 'model', 'write'], 'calls': [{'name': 'llm.classify', 'resolved_name': 'llm.classify', 'line': 3}, {'name': 'graph.merge', 'resolved_name': 'graph.merge', 'line': 6}], 'dataflow': [{'target': 'hypothesis', 'calls': ['llm.classify'], 'reads': ['llm', 'left', 'right'], 'line': 3}]}. **Why JEV:** Test reduced false merges while retaining provenance and reversible mutations. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.classify, graph.merge`; 2 branches, 0 loops, 0 exception nodes. **Intervention:** `after_candidate_generation_before_graph_mutation`.

**Questions and bounded answers:**

- `JEV-91A74DABC9DB-Q1` (choice): Do these two candidate records refer to the same real-world entity according to the identity criteria? Answers: `['same', 'related', 'different', 'uncertain']`. Evidence: `['left_record', 'right_record', 'identity_criteria', 'provenance', 'conflicting_evidence']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-91A74DABC9DB-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Do these two candidate records refer to the same real-world entity according to the identity criteria? Required evidence: left_record, right_record, identity_criteria, provenance, conflicting_evidence? Answers: `[False, True]`. Evidence: `['left_record', 'right_record', 'identity_criteria', 'provenance', 'conflicting_evidence']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.95, 'illustrative_confidence_floor': 0.9, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** unique IDs, graph schema, referential integrity, transaction, merge approval, provenance preservation.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.700 | 0.50–0.90 | 1.6 | 0.0949 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.850 | 0.65–1.00 | 1.0 | 0.0720 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.350 | 0.15–0.55 | -0.8 | -0.0237 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-91A74DABC9DB-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-B5DC8157D3F1 · expensive_or_irreversible_action

**Source:** `entities.py::reconcile`, lines 2–7; parser `python_ast`; source SHA-256 `85f8600662bd618ae47cc88401d8c77a926361e2bd3c039d09ea48cb37d408f3`.

**Why here:** {'roles': ['graph', 'model', 'write'], 'calls': [{'name': 'llm.classify', 'resolved_name': 'llm.classify', 'line': 3}, {'name': 'graph.merge', 'resolved_name': 'graph.merge', 'line': 6}], 'dataflow': [{'target': 'hypothesis', 'calls': ['llm.classify'], 'reads': ['llm', 'left', 'right'], 'line': 3}]}. **Why JEV:** Test whether semantic scope assessment catches unintended side effects before deterministic policy. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.classify, graph.merge`; 2 branches, 0 loops, 0 exception nodes. **Intervention:** `before_policy_gate`.

**Questions and bounded answers:**

- `JEV-B5DC8157D3F1-Q1` (choice): Does the proposed action exceed the explicitly authorized intent described in the evidence? Answers: `['within_intent', 'outside_intent', 'uncertain']`. Evidence: `['proposed_action', 'authorization_scope', 'user_intent', 'environment']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-B5DC8157D3F1-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the proposed action exceed the explicitly authorized intent described in the evidence? Required evidence: proposed_action, authorization_scope, user_intent, environment? Answers: `[False, True]`. Evidence: `['proposed_action', 'authorization_scope', 'user_intent', 'environment']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.95, 'illustrative_confidence_floor': 0.9, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** permissions, explicit approval, production scope, transaction boundaries, rollback readiness.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.700 | 0.50–0.90 | 1.6 | 0.0949 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.350 | 0.15–0.55 | -0.8 | -0.0237 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-B5DC8157D3F1-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-F8BA17EB6536 · final_answer_validation

**Source:** `entities.py::reconcile`, lines 2–7; parser `python_ast`; source SHA-256 `85f8600662bd618ae47cc88401d8c77a926361e2bd3c039d09ea48cb37d408f3`.

**Why here:** {'roles': ['graph', 'model', 'write'], 'calls': [{'name': 'llm.classify', 'resolved_name': 'llm.classify', 'line': 3}, {'name': 'graph.merge', 'resolved_name': 'graph.merge', 'line': 6}], 'dataflow': [{'target': 'hypothesis', 'calls': ['llm.classify'], 'reads': ['llm', 'left', 'right'], 'line': 3}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.classify, graph.merge`; 2 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-F8BA17EB6536-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-F8BA17EB6536-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** required sections, output schema, citation existence, verbatim spans, length bounds.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.700 | 0.50–0.90 | 1.6 | 0.0949 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.350 | 0.15–0.55 | -0.8 | -0.0237 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-F8BA17EB6536-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

## Coverage and unknowns

```json
{
  "languages": {
    "python": 1
  },
  "files_analyzed": 1,
  "files_considered": 2,
  "symbols": 2,
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
