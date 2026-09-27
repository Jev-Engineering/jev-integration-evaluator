# JEV integration plan

CompleteTech provider-starter

## Ranked experiment order

| ID | Tier | Timing | Fallback | Experiment |
|---|---|---|---|---|
| JEV-3AB7E6831523 | 1 | after_failure_before_retry | existing validated baseline | JEV-3AB7E6831523-EXP-01 |
| JEV-80B425907A5D | 1 | after_operation_before_advancing_subgoal | existing validated baseline | JEV-80B425907A5D-EXP-01 |
| JEV-F60068063D8D | 1 | between_observe_act_iterations | existing validated baseline | JEV-F60068063D8D-EXP-01 |
| JEV-E69F0ED1FC49 | 1 | after_operation_before_advancing_subgoal | existing validated baseline | JEV-E69F0ED1FC49-EXP-01 |
| JEV-35AB38B3026C | 1 | before_policy_gate | existing validated baseline | JEV-35AB38B3026C-EXP-01 |
| JEV-BC69C74DF3CA | 1 | after_generation_before_delivery | existing validated baseline | JEV-BC69C74DF3CA-EXP-01 |
| JEV-1EDC6846A754 | 1 | before_dispatch | existing validated baseline | JEV-1EDC6846A754-EXP-01 |
| JEV-950F0C5EFE45 | 1 | after_planning_before_execution | existing validated baseline | JEV-950F0C5EFE45-EXP-01 |
| JEV-B4B5BF2FD219 | 1 | after_generation_before_delivery | existing validated baseline | JEV-B4B5BF2FD219-EXP-01 |
| JEV-BF71FD853BBC | 1 | after_candidate_generation_before_execution | existing validated baseline | JEV-BF71FD853BBC-EXP-01 |
| JEV-0B40C24F3988 | 1 | before_context_eviction | existing validated baseline | JEV-0B40C24F3988-EXP-01 |
| JEV-1ED0191AB058 | 1 | after_generation_before_delivery | existing validated baseline | JEV-1ED0191AB058-EXP-01 |
| JEV-BD68119011F6 | 1 | before_specialist_dispatch | existing validated baseline | JEV-BD68119011F6-EXP-01 |
| JEV-C25AE1A294B1 | 1 | before_dispatch | existing validated baseline | JEV-C25AE1A294B1-EXP-01 |
| JEV-D83B745FC7BF | 1 | after_candidate_generation_before_execution | existing validated baseline | JEV-D83B745FC7BF-EXP-01 |
| JEV-E44ED530B27A | 1 | after_generation_before_delivery | existing validated baseline | JEV-E44ED530B27A-EXP-01 |
| JEV-EC417BD414AB | 1 | after_generation_before_delivery | existing validated baseline | JEV-EC417BD414AB-EXP-01 |
| JEV-47C500E9A193 | 1 | after_diff_and_tests_before_review_disposition | existing validated baseline | JEV-47C500E9A193-EXP-01 |

## Constrained sets

```json
{
  "method": "exact_enumeration",
  "optimality_proven_for_declared_model": true,
  "eligible_candidates": 0,
  "feasible_sets_examined": 1,
  "excluded": [
    {
      "candidate_id": "JEV-3AB7E6831523",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-80B425907A5D",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-F60068063D8D",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-E69F0ED1FC49",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-35AB38B3026C",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-BC69C74DF3CA",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-1EDC6846A754",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-950F0C5EFE45",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-B4B5BF2FD219",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-BF71FD853BBC",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-0B40C24F3988",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-1ED0191AB058",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-BD68119011F6",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-C25AE1A294B1",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-D83B745FC7BF",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-E44ED530B27A",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-EC417BD414AB",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-47C500E9A193",
      "reason": "Semantic review not approved"
    }
  ],
  "recommended_minimal_set": {
    "candidate_ids": [],
    "utility": 0.0,
    "quality_gain": 0,
    "reliability_gain": 0,
    "failure_reduction": 0,
    "model_call_reduction": 0,
    "measured_interaction_utility": 0,
    "added_latency_ms": 0,
    "added_cost": 0,
    "calls_per_task": 0,
    "complexity": 0
  },
  "recommended_balanced_set": {
    "candidate_ids": [],
    "utility": 0.0,
    "quality_gain": 0,
    "reliability_gain": 0,
    "failure_reduction": 0,
    "model_call_reduction": 0,
    "measured_interaction_utility": 0,
    "added_latency_ms": 0,
    "added_cost": 0,
    "calls_per_task": 0,
    "complexity": 0
  },
  "recommended_maximum_reliability_set": {
    "candidate_ids": [],
    "utility": 0.0,
    "quality_gain": 0,
    "reliability_gain": 0,
    "failure_reduction": 0,
    "model_call_reduction": 0,
    "measured_interaction_utility": 0,
    "added_latency_ms": 0,
    "added_cost": 0,
    "calls_per_task": 0,
    "complexity": 0
  },
  "pareto_display_subset": [
    {
      "candidate_ids": [],
      "utility": 0.0,
      "quality_gain": 0,
      "reliability_gain": 0,
      "failure_reduction": 0,
      "model_call_reduction": 0,
      "measured_interaction_utility": 0,
      "added_latency_ms": 0,
      "added_cost": 0,
      "calls_per_task": 0,
      "complexity": 0
    }
  ],
  "status": "no_justified_integration_set",
  "assumptions": [
    "Latency uses a conservative serial sum; replace with measured joint critical paths before rollout.",
    "Quality/reliability/failure deltas are additive hypotheses; avoid double-counting the same outcome.",
    "No positive credit for unmeasured synergy; duplicate routing decisions conflict by default.",
    "Throughput and risk are per-component feasibility checks, not an end-to-end safety guarantee.",
    "The reliability set maximizes the supplied reliability proxy, not proven end-to-end reliability.",
    "Utility coefficients and the minimal-set 80% retention target are disclosed defaults in optimizer.py."
  ]
}
```

## Interactions

```json
[
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-80B425907A5D",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-F60068063D8D",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-1EDC6846A754",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-950F0C5EFE45",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-B4B5BF2FD219",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-BF71FD853BBC",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-3AB7E6831523",
    "b": "JEV-0B40C24F3988",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-F60068063D8D",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-1EDC6846A754",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-950F0C5EFE45",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-B4B5BF2FD219",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-BF71FD853BBC",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-C25AE1A294B1",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-80B425907A5D",
    "b": "JEV-D83B745FC7BF",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-F60068063D8D",
    "b": "JEV-1EDC6846A754",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-F60068063D8D",
    "b": "JEV-950F0C5EFE45",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-F60068063D8D",
    "b": "JEV-B4B5BF2FD219",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-F60068063D8D",
    "b": "JEV-BF71FD853BBC",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-E69F0ED1FC49",
    "b": "JEV-1EDC6846A754",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-E69F0ED1FC49",
    "b": "JEV-BF71FD853BBC",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-E69F0ED1FC49",
    "b": "JEV-1ED0191AB058",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-E69F0ED1FC49",
    "b": "JEV-C25AE1A294B1",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-E69F0ED1FC49",
    "b": "JEV-D83B745FC7BF",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-35AB38B3026C",
    "b": "JEV-BC69C74DF3CA",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-35AB38B3026C",
    "b": "JEV-950F0C5EFE45",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same-file architectural hypothesis; verify call path",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-1EDC6846A754",
    "b": "JEV-950F0C5EFE45",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-1EDC6846A754",
    "b": "JEV-B4B5BF2FD219",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-1EDC6846A754",
    "b": "JEV-BF71FD853BBC",
    "kind": "redundant",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": true,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-950F0C5EFE45",
    "b": "JEV-B4B5BF2FD219",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-950F0C5EFE45",
    "b": "JEV-BF71FD853BBC",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-B4B5BF2FD219",
    "b": "JEV-BF71FD853BBC",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-0B40C24F3988",
    "b": "JEV-E44ED530B27A",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-1ED0191AB058",
    "b": "JEV-C25AE1A294B1",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-1ED0191AB058",
    "b": "JEV-D83B745FC7BF",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-BD68119011F6",
    "b": "JEV-EC417BD414AB",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-C25AE1A294B1",
    "b": "JEV-D83B745FC7BF",
    "kind": "redundant",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": true,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  }
]
```

Create a worktree, establish baseline, generate an adapter, inspect and wire the host callsite, review the content-hashed patch plan, and apply only the authorized diff. Scaffolding does not mean the integration is wired or deployed.
