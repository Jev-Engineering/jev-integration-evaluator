# JEV integration plan

CompleteTech provider-starter

## Ranked experiment order

| ID | Tier | Timing | Fallback | Experiment |
|---|---|---|---|---|
| JEV-8EF27FF99D40 | 1 | after_operation_before_advancing_subgoal | existing validated baseline | JEV-8EF27FF99D40-EXP-01 |
| JEV-0885EEC04513 | 1 | before_dispatch | existing validated baseline | JEV-0885EEC04513-EXP-01 |
| JEV-305396D636E2 | 1 | after_candidate_generation_before_execution | existing validated baseline | JEV-305396D636E2-EXP-01 |
| JEV-A36A57C9D938 | 1 | after_generation_before_delivery | existing validated baseline | JEV-A36A57C9D938-EXP-01 |

## Constrained sets

```json
{
  "method": "exact_enumeration",
  "optimality_proven_for_declared_model": true,
  "eligible_candidates": 0,
  "feasible_sets_examined": 1,
  "excluded": [
    {
      "candidate_id": "JEV-8EF27FF99D40",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-0885EEC04513",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-305396D636E2",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-A36A57C9D938",
      "reason": "Semantic review not approved"
    },
    {
      "candidate_id": "JEV-60EA7A15E386",
      "reason": "Tier 0 / rejected"
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
    "a": "JEV-8EF27FF99D40",
    "b": "JEV-0885EEC04513",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-8EF27FF99D40",
    "b": "JEV-305396D636E2",
    "kind": "complementary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-8EF27FF99D40",
    "b": "JEV-A36A57C9D938",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-0885EEC04513",
    "b": "JEV-305396D636E2",
    "kind": "redundant",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": true,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-0885EEC04513",
    "b": "JEV-A36A57C9D938",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  },
  {
    "a": "JEV-305396D636E2",
    "b": "JEV-A36A57C9D938",
    "kind": "shared_boundary",
    "status": "hypothesis",
    "utility_delta": 0.0,
    "conflict": false,
    "reason": "Same source boundary",
    "validation": "factorial ablation; measure combined critical-path latency, do not assume additive quality"
  }
]
```

Create a worktree, establish baseline, generate an adapter, inspect and wire the host callsite, review the content-hashed patch plan, and apply only the authorized diff. Scaffolding does not mean the integration is wired or deployed.
