# JEV opportunity inventory

CompleteTech provider-starter

## Executive summary

Repository: **polyglot**. Files analyzed: **3**. Candidate locations: **5**. Deterministic/anti-pattern rejections: **1**. Strong or high-leverage candidates: **0**.

All unreviewed placements remain experimental. Scores are prioritization heuristics, not measured quality gains or probabilities of usefulness. Unknown cost, latency, failure rate, and task frequency are not reported as measurements.

First experiment to review: **JEV-8EF27FF99D40** at `router.ts::opaqueSeam`. Validate the proposed boundary, record a baseline, and use offline/shadow evaluation first.

Largest risks: mislabeled boundaries, uncalibrated confidence, correlated evaluators, irreversible effects, stale evidence, and unmeasured latency/cost.

## Ranked candidate table

| Rank | ID | File / symbol | Pattern | Tier | Score [sensitivity range] | Expected benefit | Cost | Risk | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | JEV-8EF27FF99D40 | router.ts :: opaqueSeam | E | 1 | 0.541 [0.153, 0.895] | Test semantic completion rather than equating HTTP success with task success. | unknown | unknown | unknown | experimental |
| 2 | JEV-0885EEC04513 | router.ts :: opaqueSeam | C | 1 | 0.519 [0.132, 0.878] | Test bounded capability routing against the existing dispatcher. | unknown | unknown | unknown | experimental |
| 3 | JEV-305396D636E2 | router.ts :: opaqueSeam | A | 1 | 0.519 [0.132, 0.878] | Test whether bounded selection reduces invalid or unnecessary tool calls. | unknown | unknown | unknown | experimental |
| 4 | JEV-A36A57C9D938 | router.ts :: opaqueSeam | M | 1 | 0.519 [0.132, 0.878] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 5 | JEV-60EA7A15E386 | router.ts :: exactScale | NONE | 0 | 0.032 [0.000, 0.419] | Preserve deterministic computation or an appropriate generative model. | unknown | unknown | unknown | do_not_use |

## Per-candidate evidence and design

### JEV-8EF27FF99D40 · post_action_verification

**Source:** `router.ts::opaqueSeam`, lines 4–8; parser `typescript_ast`; source SHA-256 `6583005705a18decc2c20bc5a08658dd2a8b5d688297b4bc6f0f0900744c0e24`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'line': 5}, {'name': 'executor.execute_tool', 'line': 6}], 'dataflow': [{'target': 'proposed', 'calls': ['llm.choose'], 'reads': ['llm', 'choose', 'state'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'execute_tool', 'proposed'], 'line': 6}]}. **Why JEV:** Test semantic completion rather than equating HTTP success with task success. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, executor.execute_tool`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `after_operation_before_advancing_subgoal`.

**Questions and bounded answers:**

- `JEV-8EF27FF99D40-Q1` (choice): Do the observed postconditions establish that the stated subgoal was accomplished? Answers: `['succeeded', 'partial', 'failed', 'unexpected_state', 'uncertain']`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-8EF27FF99D40-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Do the observed postconditions establish that the stated subgoal was accomplished? Required evidence: subgoal, expected_postconditions, before_state, after_state, tool_result? Answers: `[False, True]`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** exit code, HTTP status, schema, exact postconditions, transaction integrity.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.850 | 0.65–1.00 | 1.0 | 0.0720 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-8EF27FF99D40-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-0885EEC04513 · tool_function_routing

**Source:** `router.ts::opaqueSeam`, lines 4–8; parser `typescript_ast`; source SHA-256 `6583005705a18decc2c20bc5a08658dd2a8b5d688297b4bc6f0f0900744c0e24`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'line': 5}, {'name': 'executor.execute_tool', 'line': 6}], 'dataflow': [{'target': 'proposed', 'calls': ['llm.choose'], 'reads': ['llm', 'choose', 'state'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'execute_tool', 'proposed'], 'line': 6}]}. **Why JEV:** Test bounded capability routing against the existing dispatcher. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, executor.execute_tool`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `before_dispatch`.

**Questions and bounded answers:**

- `JEV-0885EEC04513-Q1` (choice): Which available handler has the declared capability needed for this request? Answers: `['deterministic_handler', 'specialist', 'general_model', 'human', 'uncertain']`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-0885EEC04513-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which available handler has the declared capability needed for this request? Required evidence: request, handler_registry, capabilities, constraints? Answers: `[False, True]`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** registered handlers, argument types, handler availability, permissions.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-0885EEC04513-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-305396D636E2 · before_tool_execution

**Source:** `router.ts::opaqueSeam`, lines 4–8; parser `typescript_ast`; source SHA-256 `6583005705a18decc2c20bc5a08658dd2a8b5d688297b4bc6f0f0900744c0e24`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'line': 5}, {'name': 'executor.execute_tool', 'line': 6}], 'dataflow': [{'target': 'proposed', 'calls': ['llm.choose'], 'reads': ['llm', 'choose', 'state'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'execute_tool', 'proposed'], 'line': 6}]}. **Why JEV:** Test whether bounded selection reduces invalid or unnecessary tool calls. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, executor.execute_tool`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `after_candidate_generation_before_execution`.

**Questions and bounded answers:**

- `JEV-305396D636E2-Q1` (choice): Which legal candidate action advances the stated subgoal using the supplied evidence? Answers: `['inspect', 'search', 'edit', 'test', 'escalate', 'uncertain']`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-305396D636E2-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which legal candidate action advances the stated subgoal using the supplied evidence? Required evidence: objective, subgoal, legal_candidates, state, recent_actions? Answers: `[False, True]`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** tool allowlist, argument schema, resource scope, authorization, idempotency.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-305396D636E2-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-A36A57C9D938 · final_answer_validation

**Source:** `router.ts::opaqueSeam`, lines 4–8; parser `typescript_ast`; source SHA-256 `6583005705a18decc2c20bc5a08658dd2a8b5d688297b4bc6f0f0900744c0e24`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'line': 5}, {'name': 'executor.execute_tool', 'line': 6}], 'dataflow': [{'target': 'proposed', 'calls': ['llm.choose'], 'reads': ['llm', 'choose', 'state'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'execute_tool', 'proposed'], 'line': 6}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, executor.execute_tool`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-A36A57C9D938-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-A36A57C9D938-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** required sections, output schema, citation existence, verbatim spans, length bounds.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.400 | 0.20–0.60 | 1.0 | 0.0339 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-A36A57C9D938-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-60EA7A15E386 · deterministic_or_generative_antipattern

**Source:** `router.ts::exactScale`, lines 9–9; parser `typescript_ast`; source SHA-256 `1395aa9cd10bb83880c1c8eddfeb8bb0a617b0e69d824cffce62d9caac3d34df`.

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

**Test:** `JEV-60EA7A15E386-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

## Coverage and unknowns

```json
{
  "languages": {
    "rust": 1,
    "go": 1,
    "typescript": 1
  },
  "files_analyzed": 3,
  "files_considered": 5,
  "symbols": 4,
  "truncated": false,
  "parser_counts": {
    "lexical_review_only": 2,
    "typescript_ast": 1
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
