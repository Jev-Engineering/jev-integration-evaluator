# JEV opportunity inventory

CompleteTech provider-starter

## Executive summary

Repository: **synthetic-agent**. Files analyzed: **2**. Candidate locations: **18**. Deterministic/anti-pattern rejections: **0**. Strong or high-leverage candidates: **0**.

All unreviewed placements remain experimental. Scores are prioritization heuristics, not measured quality gains or probabilities of usefulness. Unknown cost, latency, failure rate, and task frequency are not reported as measurements.

First experiment to review: **JEV-3AB7E6831523** at `agent.py::run_steps`. Validate the proposed boundary, record a baseline, and use offline/shadow evaluation first.

Largest risks: mislabeled boundaries, uncalibrated confidence, correlated evaluators, irreversible effects, stale evidence, and unmeasured latency/cost.

## Ranked candidate table

| Rank | ID | File / symbol | Pattern | Tier | Score [sensitivity range] | Expected benefit | Cost | Risk | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | JEV-3AB7E6831523 | agent.py :: run_steps | I | 1 | 0.579 [0.192, 0.933] | Test reduced repetition and recovery calls, retaining deterministic backoff. | unknown | unknown | unknown | experimental |
| 2 | JEV-80B425907A5D | agent.py :: run_steps | E | 1 | 0.579 [0.192, 0.933] | Test semantic completion rather than equating HTTP success with task success. | unknown | unknown | unknown | experimental |
| 3 | JEV-F60068063D8D | agent.py :: run_steps | F | 1 | 0.579 [0.192, 0.933] | Test fewer unproductive iterations and premature completions. | unknown | unknown | unknown | experimental |
| 4 | JEV-E69F0ED1FC49 | agent.py :: dispatch_once | E | 1 | 0.571 [0.184, 0.925] | Test semantic completion rather than equating HTTP success with task success. | unknown | unknown | unknown | experimental |
| 5 | JEV-35AB38B3026C | agent.py :: publish_proposal | B | 1 | 0.570 [0.183, 0.929] | Test whether semantic scope assessment catches unintended side effects before deterministic policy. | unknown | unknown | unknown | experimental |
| 6 | JEV-BC69C74DF3CA | agent.py :: publish_proposal | M | 1 | 0.570 [0.183, 0.929] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 7 | JEV-1EDC6846A754 | agent.py :: run_steps | C | 1 | 0.558 [0.171, 0.917] | Test bounded capability routing against the existing dispatcher. | unknown | unknown | unknown | experimental |
| 8 | JEV-950F0C5EFE45 | agent.py :: run_steps | G | 1 | 0.558 [0.171, 0.917] | Test pre-execution detection of semantic dependency errors. | unknown | unknown | unknown | experimental |
| 9 | JEV-B4B5BF2FD219 | agent.py :: run_steps | M | 1 | 0.558 [0.171, 0.917] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 10 | JEV-BF71FD853BBC | agent.py :: run_steps | A | 1 | 0.558 [0.171, 0.917] | Test whether bounded selection reduces invalid or unnecessary tool calls. | unknown | unknown | unknown | experimental |
| 11 | JEV-0B40C24F3988 | agent.py :: retain_history | H | 1 | 0.550 [0.163, 0.908] | Test relevance-based retention; a generative model still performs any summarization. | unknown | unknown | unknown | experimental |
| 12 | JEV-1ED0191AB058 | agent.py :: dispatch_once | M | 1 | 0.550 [0.163, 0.908] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 13 | JEV-BD68119011F6 | agent.py :: distribute | J | 1 | 0.550 [0.163, 0.908] | Test reduced misrouting without granting additional agent permissions. | unknown | unknown | unknown | experimental |
| 14 | JEV-C25AE1A294B1 | agent.py :: dispatch_once | C | 1 | 0.550 [0.163, 0.908] | Test bounded capability routing against the existing dispatcher. | unknown | unknown | unknown | experimental |
| 15 | JEV-D83B745FC7BF | agent.py :: dispatch_once | A | 1 | 0.550 [0.163, 0.908] | Test whether bounded selection reduces invalid or unnecessary tool calls. | unknown | unknown | unknown | experimental |
| 16 | JEV-E44ED530B27A | agent.py :: retain_history | M | 1 | 0.550 [0.163, 0.908] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 17 | JEV-EC417BD414AB | agent.py :: distribute | M | 1 | 0.550 [0.163, 0.908] | Test atomic evidence checks before a separate revision step. | unknown | unknown | unknown | experimental |
| 18 | JEV-47C500E9A193 | agent.py :: review_change | K | 1 | 0.417 [0.030, 0.786] | Test atomic review checks, never automatic permission to merge. | unknown | unknown | unknown | experimental |

## Per-candidate evidence and design

### JEV-3AB7E6831523 · retry_recovery

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test reduced repetition and recovery calls, retaining deterministic backoff. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `after_failure_before_retry`.

**Questions and bounded answers:**

- `JEV-3AB7E6831523-Q1` (choice): Which recovery strategy is supported by the error evidence and previous attempted fixes? Answers: `['retry_same', 'retry_modified', 'inspect', 'alternate_tool', 'replan', 'rollback', 'escalate', 'abort', 'uncertain']`. Evidence: `['error', 'previous_attempts', 'state', 'legal_recovery_actions']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-3AB7E6831523-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which recovery strategy is supported by the error evidence and previous attempted fixes? Required evidence: error, previous_attempts, state, legal_recovery_actions? Answers: `[False, True]`. Evidence: `['error', 'previous_attempts', 'state', 'legal_recovery_actions']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** retry ceiling, backoff, transient status codes, idempotency, rollback authority.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.850 | 0.65–1.00 | 1.0 | 0.0720 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-3AB7E6831523-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-80B425907A5D · post_action_verification

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test semantic completion rather than equating HTTP success with task success. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `after_operation_before_advancing_subgoal`.

**Questions and bounded answers:**

- `JEV-80B425907A5D-Q1` (choice): Do the observed postconditions establish that the stated subgoal was accomplished? Answers: `['succeeded', 'partial', 'failed', 'unexpected_state', 'uncertain']`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-80B425907A5D-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Do the observed postconditions establish that the stated subgoal was accomplished? Required evidence: subgoal, expected_postconditions, before_state, after_state, tool_result? Answers: `[False, True]`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-80B425907A5D-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-F60068063D8D · agent_loop_transition

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test fewer unproductive iterations and premature completions. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `between_observe_act_iterations`.

**Questions and bounded answers:**

- `JEV-F60068063D8D-Q1` (choice): Which transition is justified by the current goal, observed state, and unresolved blockers? Answers: `['continue', 'gather_evidence', 'replan', 'complete', 'human', 'uncertain']`. Evidence: `['goal', 'state', 'completion_conditions', 'blockers', 'recent_progress']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-F60068063D8D-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which transition is justified by the current goal, observed state, and unresolved blockers? Required evidence: goal, state, completion_conditions, blockers, recent_progress? Answers: `[False, True]`. Evidence: `['goal', 'state', 'completion_conditions', 'blockers', 'recent_progress']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** step budget, time budget, state invariants, legal transitions, verified completion.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.850 | 0.65–1.00 | 1.0 | 0.0720 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-F60068063D8D-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-E69F0ED1FC49 · post_action_verification

**Source:** `agent.py::dispatch_once`, lines 4–9; parser `python_ast`; source SHA-256 `3f27ed7bc19ecfb5751f4c766f799fb6d4dc4d7c2a993357e7220e1d777d44ae`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 5}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 5}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 7}], 'dataflow': [{'target': 'proposal', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'objective', 'tuple', 'registry'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 7}]}. **Why JEV:** Test semantic completion rather than equating HTTP success with task success. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, executor.execute_tool`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_operation_before_advancing_subgoal`.

**Questions and bounded answers:**

- `JEV-E69F0ED1FC49-Q1` (choice): Do the observed postconditions establish that the stated subgoal was accomplished? Answers: `['succeeded', 'partial', 'failed', 'unexpected_state', 'uncertain']`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-E69F0ED1FC49-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Do the observed postconditions establish that the stated subgoal was accomplished? Required evidence: subgoal, expected_postconditions, before_state, after_state, tool_result? Answers: `[False, True]`. Evidence: `['subgoal', 'expected_postconditions', 'before_state', 'after_state', 'tool_result']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-E69F0ED1FC49-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-35AB38B3026C · expensive_or_irreversible_action

**Source:** `agent.py::publish_proposal`, lines 46–50; parser `python_ast`; source SHA-256 `ef45f379dbe79bbd3a2ea5b442c785f920d43d8aa280e803ae83e4dd8fc49546`.

**Why here:** {'roles': ['model', 'write'], 'calls': [{'name': 'llm.generate', 'resolved_name': 'llm.generate', 'line': 47}, {'name': 'publisher.publish', 'resolved_name': 'publisher.publish', 'line': 49}], 'dataflow': [{'target': 'draft', 'calls': ['llm.generate'], 'reads': ['llm', 'request'], 'line': 47}]}. **Why JEV:** Test whether semantic scope assessment catches unintended side effects before deterministic policy. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.generate, publisher.publish`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `before_policy_gate`.

**Questions and bounded answers:**

- `JEV-35AB38B3026C-Q1` (choice): Does the proposed action exceed the explicitly authorized intent described in the evidence? Answers: `['within_intent', 'outside_intent', 'uncertain']`. Evidence: `['proposed_action', 'authorization_scope', 'user_intent', 'environment']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-35AB38B3026C-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the proposed action exceed the explicitly authorized intent described in the evidence? Required evidence: proposed_action, authorization_scope, user_intent, environment? Answers: `[False, True]`. Evidence: `['proposed_action', 'authorization_scope', 'user_intent', 'environment']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-35AB38B3026C-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-BC69C74DF3CA · final_answer_validation

**Source:** `agent.py::publish_proposal`, lines 46–50; parser `python_ast`; source SHA-256 `ef45f379dbe79bbd3a2ea5b442c785f920d43d8aa280e803ae83e4dd8fc49546`.

**Why here:** {'roles': ['model', 'write'], 'calls': [{'name': 'llm.generate', 'resolved_name': 'llm.generate', 'line': 47}, {'name': 'publisher.publish', 'resolved_name': 'publisher.publish', 'line': 49}], 'dataflow': [{'target': 'draft', 'calls': ['llm.generate'], 'reads': ['llm', 'request'], 'line': 47}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.generate, publisher.publish`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-BC69C74DF3CA-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-BC69C74DF3CA-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-BC69C74DF3CA-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-1EDC6846A754 · tool_function_routing

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test bounded capability routing against the existing dispatcher. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `before_dispatch`.

**Questions and bounded answers:**

- `JEV-1EDC6846A754-Q1` (choice): Which available handler has the declared capability needed for this request? Answers: `['deterministic_handler', 'specialist', 'general_model', 'human', 'uncertain']`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-1EDC6846A754-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which available handler has the declared capability needed for this request? Required evidence: request, handler_registry, capabilities, constraints? Answers: `[False, True]`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-1EDC6846A754-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-950F0C5EFE45 · planner_executor_boundary

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test pre-execution detection of semantic dependency errors. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `after_planning_before_execution`.

**Questions and bounded answers:**

- `JEV-950F0C5EFE45-Q1` (choice): Does the next plan step have unresolved dependencies in the supplied state? Answers: `['resolved', 'unresolved', 'uncertain']`. Evidence: `['goal', 'plan', 'next_step', 'dependency_state', 'constraints']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-950F0C5EFE45-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the next plan step have unresolved dependencies in the supplied state? Required evidence: goal, plan, next_step, dependency_state, constraints? Answers: `[False, True]`. Evidence: `['goal', 'plan', 'next_step', 'dependency_state', 'constraints']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** dependency DAG, step schema, approval, resource budget, executor allowlist.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.850 | 0.65–1.00 | 1.6 | 0.1153 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-950F0C5EFE45-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-B4B5BF2FD219 · final_answer_validation

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-B4B5BF2FD219-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-B4B5BF2FD219-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-B4B5BF2FD219-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-BF71FD853BBC · before_tool_execution

**Source:** `agent.py::run_steps`, lines 12–23; parser `python_ast`; source SHA-256 `6013cb2b676b49539ef0cfb76cdceda0775455d5bfb7a8f28d04fca754ba5c0a`.

**Why here:** {'roles': ['deterministic', 'model', 'observe', 'plan', 'tool'], 'calls': [{'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 13}, {'name': 'range', 'resolved_name': 'range', 'line': 14}, {'name': 'environment.observe', 'resolved_name': 'environment.observe', 'line': 15}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 17}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 18}, {'name': 'planner.plan', 'resolved_name': 'planner.plan', 'line': 22}], 'dataflow': [{'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 13}, {'target': 'observation', 'calls': ['environment.observe'], 'reads': ['environment'], 'line': 15}, {'target': 'proposal', 'calls': ['llm.choose'], 'reads': ['llm', 'plan', 'observation'], 'line': 17}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 18}, {'target': 'plan', 'calls': ['planner.plan'], 'reads': ['planner', 'objective'], 'line': 22}]}. **Why JEV:** Test whether bounded selection reduces invalid or unnecessary tool calls. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `planner.plan, range, environment.observe, llm.choose, executor.execute_tool, planner.plan`; 1 branches, 1 loops, 2 exception nodes. **Intervention:** `after_candidate_generation_before_execution`.

**Questions and bounded answers:**

- `JEV-BF71FD853BBC-Q1` (choice): Which legal candidate action advances the stated subgoal using the supplied evidence? Answers: `['inspect', 'search', 'edit', 'test', 'escalate', 'uncertain']`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-BF71FD853BBC-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which legal candidate action advances the stated subgoal using the supplied evidence? Required evidence: objective, subgoal, legal_candidates, state, recent_actions? Answers: `[False, True]`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| observability | 0.750 | 0.55–0.95 | 0.5 | 0.0318 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 1.000 | 1.00–1.00 | 0.8 | 0.0678 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.400 | 0.20–0.60 | -0.8 | -0.0271 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-BF71FD853BBC-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-0B40C24F3988 · context_and_compaction

**Source:** `agent.py::retain_history`, lines 26–30; parser `python_ast`; source SHA-256 `2aac23b01d8d96c472455628733c37409f6008243e9b720796cb7f342fbf5ec6`.

**Why here:** {'roles': ['context', 'deterministic', 'model'], 'calls': [{'name': 'memory.load', 'resolved_name': 'memory.load', 'line': 27}, {'name': 'len', 'resolved_name': 'len', 'line': 28}, {'name': 'memory.prune', 'resolved_name': 'memory.prune', 'line': 29}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 29}], 'dataflow': [{'target': 'entries', 'calls': ['memory.load'], 'reads': ['memory'], 'line': 27}]}. **Why JEV:** Test relevance-based retention; a generative model still performs any summarization. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `memory.load, len, memory.prune, llm.choose`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `before_context_eviction`.

**Questions and bounded answers:**

- `JEV-0B40C24F3988-Q1` (choice): Does this context item contain an unresolved constraint or fact necessary for the current task? Answers: `['keep', 'compress', 'drop', 'uncertain']`. Evidence: `['current_task', 'context_item', 'unresolved_constraints', 'superseding_evidence']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-0B40C24F3988-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does this context item contain an unresolved constraint or fact necessary for the current task? Required evidence: current_task, context_item, unresolved_constraints, superseding_evidence? Answers: `[False, True]`. Evidence: `['current_task', 'context_item', 'unresolved_constraints', 'superseding_evidence']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** pinned instructions, source references, token counting, unresolved constraint retention, user pruning choice.

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-0B40C24F3988-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-1ED0191AB058 · final_answer_validation

**Source:** `agent.py::dispatch_once`, lines 4–9; parser `python_ast`; source SHA-256 `3f27ed7bc19ecfb5751f4c766f799fb6d4dc4d7c2a993357e7220e1d777d44ae`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 5}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 5}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 7}], 'dataflow': [{'target': 'proposal', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'objective', 'tuple', 'registry'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 7}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, executor.execute_tool`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-1ED0191AB058-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-1ED0191AB058-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-1ED0191AB058-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-BD68119011F6 · multi_agent_routing

**Source:** `agent.py::distribute`, lines 33–37; parser `python_ast`; source SHA-256 `2a6ddd576685fb599ee69e65bb1b4530063d1cb79856a5d2043b081d17b1dc5a`.

**Why here:** {'roles': ['agent', 'model'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 34}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 34}, {'name': 'agents[specialist]', 'resolved_name': 'agents[specialist]', 'line': 36}], 'dataflow': [{'target': 'specialist', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'subtask', 'tuple', 'agents'], 'line': 34}]}. **Why JEV:** Test reduced misrouting without granting additional agent permissions. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, agents[specialist]`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `before_specialist_dispatch`.

**Questions and bounded answers:**

- `JEV-BD68119011F6-Q1` (choice): Which registered specialist capability best matches this bounded subtask? Answers: `['coding', 'research', 'testing', 'security', 'review', 'data', 'human', 'uncertain']`. Evidence: `['subtask', 'specialist_capabilities', 'allowed_agents', 'budget']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-BD68119011F6-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which registered specialist capability best matches this bounded subtask? Required evidence: subtask, specialist_capabilities, allowed_agents, budget? Answers: `[False, True]`. Evidence: `['subtask', 'specialist_capabilities', 'allowed_agents', 'budget']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.9, 'illustrative_confidence_floor': 0.75, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** registered agents, budget, concurrency, least privilege, delegation depth.

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-BD68119011F6-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-C25AE1A294B1 · tool_function_routing

**Source:** `agent.py::dispatch_once`, lines 4–9; parser `python_ast`; source SHA-256 `3f27ed7bc19ecfb5751f4c766f799fb6d4dc4d7c2a993357e7220e1d777d44ae`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 5}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 5}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 7}], 'dataflow': [{'target': 'proposal', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'objective', 'tuple', 'registry'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 7}]}. **Why JEV:** Test bounded capability routing against the existing dispatcher. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, executor.execute_tool`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `before_dispatch`.

**Questions and bounded answers:**

- `JEV-C25AE1A294B1-Q1` (choice): Which available handler has the declared capability needed for this request? Answers: `['deterministic_handler', 'specialist', 'general_model', 'human', 'uncertain']`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-C25AE1A294B1-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which available handler has the declared capability needed for this request? Required evidence: request, handler_registry, capabilities, constraints? Answers: `[False, True]`. Evidence: `['request', 'handler_registry', 'capabilities', 'constraints']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-C25AE1A294B1-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-D83B745FC7BF · before_tool_execution

**Source:** `agent.py::dispatch_once`, lines 4–9; parser `python_ast`; source SHA-256 `3f27ed7bc19ecfb5751f4c766f799fb6d4dc4d7c2a993357e7220e1d777d44ae`.

**Why here:** {'roles': ['model', 'tool'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 5}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 5}, {'name': 'executor.execute_tool', 'resolved_name': 'executor.execute_tool', 'line': 7}], 'dataflow': [{'target': 'proposal', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'objective', 'tuple', 'registry'], 'line': 5}, {'target': 'result', 'calls': ['executor.execute_tool'], 'reads': ['executor', 'proposal'], 'line': 7}]}. **Why JEV:** Test whether bounded selection reduces invalid or unnecessary tool calls. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, executor.execute_tool`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_candidate_generation_before_execution`.

**Questions and bounded answers:**

- `JEV-D83B745FC7BF-Q1` (choice): Which legal candidate action advances the stated subgoal using the supplied evidence? Answers: `['inspect', 'search', 'edit', 'test', 'escalate', 'uncertain']`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-D83B745FC7BF-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Which legal candidate action advances the stated subgoal using the supplied evidence? Required evidence: objective, subgoal, legal_candidates, state, recent_actions? Answers: `[False, True]`. Evidence: `['objective', 'subgoal', 'legal_candidates', 'state', 'recent_actions']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-D83B745FC7BF-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-E44ED530B27A · final_answer_validation

**Source:** `agent.py::retain_history`, lines 26–30; parser `python_ast`; source SHA-256 `2aac23b01d8d96c472455628733c37409f6008243e9b720796cb7f342fbf5ec6`.

**Why here:** {'roles': ['context', 'deterministic', 'model'], 'calls': [{'name': 'memory.load', 'resolved_name': 'memory.load', 'line': 27}, {'name': 'len', 'resolved_name': 'len', 'line': 28}, {'name': 'memory.prune', 'resolved_name': 'memory.prune', 'line': 29}, {'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 29}], 'dataflow': [{'target': 'entries', 'calls': ['memory.load'], 'reads': ['memory'], 'line': 27}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `memory.load, len, memory.prune, llm.choose`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-E44ED530B27A-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-E44ED530B27A-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-E44ED530B27A-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-EC417BD414AB · final_answer_validation

**Source:** `agent.py::distribute`, lines 33–37; parser `python_ast`; source SHA-256 `2a6ddd576685fb599ee69e65bb1b4530063d1cb79856a5d2043b081d17b1dc5a`.

**Why here:** {'roles': ['agent', 'model'], 'calls': [{'name': 'llm.choose', 'resolved_name': 'llm.choose', 'line': 34}, {'name': 'tuple', 'resolved_name': 'tuple', 'line': 34}, {'name': 'agents[specialist]', 'resolved_name': 'agents[specialist]', 'line': 36}], 'dataflow': [{'target': 'specialist', 'calls': ['llm.choose', 'tuple'], 'reads': ['llm', 'subtask', 'tuple', 'agents'], 'line': 34}]}. **Why JEV:** Test atomic evidence checks before a separate revision step. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `llm.choose, tuple, agents[specialist]`; 1 branches, 0 loops, 0 exception nodes. **Intervention:** `after_generation_before_delivery`.

**Questions and bounded answers:**

- `JEV-EC417BD414AB-Q1` (choice): Does the cited evidence support this specific generated claim in its original context? Answers: `['supported', 'contradicted', 'unsupported', 'uncertain']`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-EC417BD414AB-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the cited evidence support this specific generated claim in its original context? Required evidence: request, claim, citation, source_context? Answers: `[False, True]`. Evidence: `['request', 'claim', 'citation', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

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
| implementation_complexity | 0.300 | 0.10–0.50 | -0.8 | -0.0203 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.850 | 0.65–1.00 | 0.7 | 0.0504 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-EC417BD414AB-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

### JEV-47C500E9A193 · code_review_gate

**Source:** `agent.py::review_change`, lines 40–43; parser `python_ast`; source SHA-256 `ecfddba2ae7e78f9315ff7275dd7064dbd06e8e1e64d51697aedea11be90f121`.

**Why here:** {'roles': ['review'], 'calls': [{'name': 'reviewer.get_diff', 'resolved_name': 'reviewer.get_diff', 'line': 41}, {'name': 'reviewer.run_tests', 'resolved_name': 'reviewer.run_tests', 'line': 42}, {'name': 'reviewer.review', 'resolved_name': 'reviewer.review', 'line': 43}], 'dataflow': [{'target': 'diff', 'calls': ['reviewer.get_diff'], 'reads': ['reviewer', 'patch'], 'line': 41}, {'target': 'test_results', 'calls': ['reviewer.run_tests'], 'reads': ['reviewer', 'patch'], 'line': 42}]}. **Why JEV:** Test atomic review checks, never automatic permission to merge. This is a hypothesis, not an observed improvement.

**Why not deterministic code:** alternative classified `weak`.  Exact checks remain in the host. **Why now:** ranking combines semantic boundedness, downstream leverage and testability with cost/latency/complexity penalties; unresolved dimensions must be reviewed.

**Current architecture:** calls `reviewer.get_diff, reviewer.run_tests, reviewer.review`; 0 branches, 0 loops, 0 exception nodes. **Intervention:** `after_diff_and_tests_before_review_disposition`.

**Questions and bounded answers:**

- `JEV-47C500E9A193-Q1` (choice): Does the supplied diff implement the specific acceptance criterion under review? Answers: `['satisfied', 'not_satisfied', 'uncertain']`. Evidence: `['acceptance_criterion', 'diff', 'test_results', 'source_context']`. Keep selected-label probability and provider distribution-confidence separate; validate both on held-out data.
- `JEV-47C500E9A193-Q2` (noul): Is the supplied evidence substantively adequate to answer this specific question: Does the supplied diff implement the specific acceptance criterion under review? Required evidence: acceptance_criterion, diff, test_results, source_context? Answers: `[False, True]`. Evidence: `['acceptance_criterion', 'diff', 'test_results', 'source_context']`. Noul is P(yes), not confidence or P(the primary answer is correct).

**Policy / fallback:** `{'default_mode': 'off', 'thresholds_status': 'unvalidated', 'requires_calibration_before_active': True, 'decision_owner': 'deterministic_host', 'hard_blocks_override_model': True, 'illustrative_probability_floor': 0.95, 'illustrative_confidence_floor': 0.9, 'inspect_probability_floor': 0.65, 'timeout_ms': 2000, 'bypass': ['feature disabled', 'deterministic result sufficient', 'unchanged valid cached state', 'budget or deadline exhausted'], 'cache': 'only immutable/pinned state, evidence, candidate set, model, and policy; never cache authorization'}`. Fallback: `{'low_confidence': 'existing validated baseline or inspect', 'unavailable': 'existing validated baseline', 'unsafe_baseline': 'block or request authorized review'}`.

**Deterministic checks:** CI status, required approvals, signature rules, branch protections, scope checks.

**Score explanation:** clip(sum(weight*dimension)/sum(positive weights),0,1). The range is a dimension-sensitivity envelope, **not** a statistical confidence interval.

| Dimension | Value | Range | Weight | Contribution | Evidence status | Rationale |
|---|---|---|---|---|---|---|
| semantic_uncertainty | 0.500 | 0.30–0.70 | 1.6 | 0.0678 | inferred | Model/semantic pipeline proxy; not measured task ambiguity |
| decision_boundedness | 0.950 | 0.75–1.00 | 1.5 | 0.1208 | inferred | A candidate bounded rubric exists; validate coverage and label exclusivity |
| downstream_consequence | 0.550 | 0.35–0.75 | 1.6 | 0.0746 | inferred | Static reachability and side-effect proxy; not a causal estimate |
| decision_frequency | 0.500 | 0.00–1.00 | 0.5 | 0.0212 | unknown | Requires source-correlated task traces |
| cost_of_wrong_decision | 0.500 | 0.00–1.00 | 1.2 | 0.0508 | unknown | Requires failure costs or impact estimates from the owner |
| recoverability_value | 0.600 | 0.40–0.80 | 1.0 | 0.0508 | inferred | Pattern-specific opportunity to detect or recover failures |
| observability | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Observation/verification call sightings |
| deterministic_alternative_quality | 0.200 | 0.00–0.40 | -2.4 | -0.0407 | inferred | Explicit anti-pattern gate, or unresolved semantic need |
| current_failure_rate | 0.500 | 0.00–1.00 | 0.9 | 0.0381 | unknown | No empirical failure rate inferred from source |
| current_llm_dependency | 0.000 | 0.00–0.00 | 0.8 | 0.0000 | observed | Recognized concrete model-call signature |
| latency_sensitivity | 0.500 | 0.00–1.00 | -1.2 | -0.0508 | unknown | Owner budget and measured critical path required |
| cost_sensitivity | 0.500 | 0.00–1.00 | -0.7 | -0.0297 | unknown | Owner budget and prices required |
| implementation_complexity | 0.250 | 0.05–0.45 | -0.8 | -0.0169 | inferred | Local branch/exception proxy; integration work may differ |
| testability | 0.800 | 0.60–1.00 | 1.0 | 0.0678 | inferred | Repository test presence proxy, not candidate test coverage |
| expected_reuse | 0.400 | 0.20–0.60 | 0.5 | 0.0169 | inferred | Static call fan-out proxy; downstream fan-out is not runtime reuse |
| confidence_calibration_value | 0.500 | 0.30–0.70 | 0.7 | 0.0297 | inferred | Potential value of abstention at this boundary |

**What could make this wrong:** `['Incorrect high-confidence classification', 'Added latency/cost', 'Evidence loss or stale state', 'Correlated evaluator errors']`; `[]`. **Expected impact / added latency / cost:** unmeasured unless explicitly supplied in `estimates`.

**Implementation sketch:** generate legal candidates and evidence → typed assessment → explicit host policy → deterministic executor → observed postconditions. Keep feature off until a reviewed experiment requires it.

**Test:** `JEV-47C500E9A193-EXP-01`; unit boundary tests, invalid responses, outages/timeouts, low confidence, permissions, paired task replay, resource measurement, and held-out calibration.

## Coverage and unknowns

```json
{
  "languages": {
    "python": 2
  },
  "files_analyzed": 2,
  "files_considered": 4,
  "symbols": 10,
  "truncated": false,
  "parser_counts": {
    "python_ast": 2
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
