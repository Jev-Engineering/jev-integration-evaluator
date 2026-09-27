# JEV experiment plan

CompleteTech provider-starter

## Before behavior changes

Freeze the code revision, task hashes, model ID, rubric hash, policy version, random seeds, failure taxonomy, minimum useful effect, risk/cost/latency limits, and stopping rule. Reuse the same task instances. Randomize order or assignment at task/episode level; isolate stateful replays. Hold out all threshold and question-selection test data.

Primary metric: verified task success. Minimum useful absolute effect: 0.020. Minimum independent clusters for an adoption decision: 30 (a screening default, not a power calculation).

Record success/failure, quality, cost, tokens, model/tool calls, retries, latency, human escalations, unsafe actions, unsafe actions prevented, false blocks, replans, and independently verified progress. Keep timeouts and invalid model outputs. Decision replay measures decision accuracy only; shadow disagreement is not a rescue.

Compare rescues/regressions, absolute/relative effects, paired cluster bootstrap intervals, paired Dirichlet or cluster Bayesian-bootstrap usefulness, efficiency, failure transitions and Pareto point estimates. Use factorial ablations, independent judging, Holm correction for exploratory McNemar comparisons, and an untouched final holdout. Report calibration, subgroup error and coverage.

Canary requires frozen calibration and host approval. Roll back on unsafe actions, excess failure/false-block rate, p95 latency, cost, or fallback limits. No active deployment follows automatically from a score or a p-value. Test feature-off parity, outages, malformed labels, wrong model, deadlines, budgets, stale caches, approval refusal and state changes.

```json
{
  "schema_version": "1.0",
  "scan_fingerprint": "9d3be3a0ce9a9770dc74cb65f457cc879556095e47e485ffca472ea17402ba81",
  "candidate_ids": [
    "JEV-3AB7E6831523",
    "JEV-80B425907A5D",
    "JEV-F60068063D8D",
    "JEV-E69F0ED1FC49",
    "JEV-35AB38B3026C",
    "JEV-BC69C74DF3CA",
    "JEV-1EDC6846A754",
    "JEV-950F0C5EFE45",
    "JEV-B4B5BF2FD219",
    "JEV-BF71FD853BBC",
    "JEV-0B40C24F3988",
    "JEV-1ED0191AB058",
    "JEV-BD68119011F6",
    "JEV-C25AE1A294B1",
    "JEV-D83B745FC7BF",
    "JEV-E44ED530B27A",
    "JEV-EC417BD414AB",
    "JEV-47C500E9A193"
  ],
  "primary_metric": "verified task success",
  "minimum_useful_effect": 0.02,
  "assignment_unit": "task or independent episode",
  "pairing_keys": [
    "task_id",
    "replicate",
    "task_hash",
    "dataset_id",
    "seed"
  ],
  "arms": [
    "baseline",
    "router",
    "verifier",
    "router_verifier"
  ],
  "split_policy": "calibration separate from frozen test",
  "status": "planned_not_run",
  "validation": {
    "paired_replay": true,
    "bootstrap_samples": 2000,
    "bayesian_samples": 5000,
    "confidence_level": 0.95,
    "minimum_useful_effect": 0.02,
    "min_pairs": 30,
    "seed": 731,
    "shadow_mode": true
  }
}
```
