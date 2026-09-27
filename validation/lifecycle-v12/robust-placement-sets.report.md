# JEV scenario-robust placement selection

Status: **conditional_robust_placement_set**.

These are conditional design choices, not observed effectiveness or deployment approval.

| Choice | Candidates | Worst utility | Worst calls | Maximum regret |
|---|---|---:|---:|---:|
| recommended_minimal_set | JEV-80B425907A5D | 0.099400 | 1.000 | 0.279400 |
| recommended_balanced_set | JEV-80B425907A5D | 0.099400 | 1.000 | 0.279400 |
| minimax_regret_set | JEV-3AB7E6831523, JEV-80B425907A5D | -0.021200 | 2.000 | 0.120600 |

## Declared scenarios

nominal: synthetic. Fabricated demo assumptions, not model measurements.
adverse: synthetic. Fabricated stress assumptions; not a confidence interval.

## Assumptions and limits

Scenarios are user-declared sensitivity cases, not assigned probabilities or confidence intervals.

Feasibility must hold in every supplied scenario; omitted scenarios are not covered.

Utility deltas remain additive hypotheses; joint resource/interaction measurements are preferable.

Latency is a serial sum; risk/throughput limits are per placement, not end-to-end guarantees.

Minimax regret compares only sets feasible across all scenarios, not each scenario's unrestricted oracle.

Positive interaction credit requires an explicit measured status and provenance; negative assumed penalties are allowed.

Beam results and their regret comparator cover only retained states and are not optimality proofs.
