# Placement-set optimization

The optimizer produces minimal, balanced and maximum-reliability sets, not “enable every candidate.” It admits only nonrejected, semantically approved candidates with provenance and complete estimates: quality gain, reliability gain, failure reduction, model-call reduction, added latency/cost/calls, complexity, maintenance, false-positive/negative rates, risk and throughput.

All resource estimates must use a common declared per-task denominator. Latency uses a conservative serial sum; cost/calls/complexity sum across placements. Risk and throughput are per-component constraints, not an end-to-end reliability proof. Missing inputs exclude a candidate; zero is only valid as an explicitly supported value. Estimated false-positive/negative rates and risk are bounded to [0,1].

Default utility is quality gain + reliability gain + 0.5 × failure reduction + 0.05 × model-call reduction, minus 0.1 × maintenance, false-positive and false-negative rates, 0.15 × the used cost-budget fraction, 0.10 × the used latency-budget fraction and 0.08 × the used complexity-budget fraction. These disclosed engineering preferences are not universal units of business value. Avoid double-counting correlated quality, reliability and failure outcomes; supply independent proxies or zero redundant terms.

Conflicting combinations are rejected. Interaction utility contributes only when explicitly marked measured; mere complementary-pattern hypotheses receive zero positive credit. Do not call a combined latency estimate measured unless the joint critical path was actually benchmarked.

For up to 18 eligible candidates, the default engine enumerates every subset and proves optimality **only for the declared simplified objective and constraints**. `--exact-limit` can range from 0 to 22. Above the limit, bounded beam search is explicitly approximate; it can miss an optimal combination. A displayed Pareto subset retains at most the highest-utility 512 candidates plus designated extremes, not a claim of the full mathematical frontier.

The balanced set maximizes declared utility. The minimal set minimizes calls and then count/cost while retaining at least 80% of positive balanced utility. The maximum-reliability set maximizes the supplied reliability proxy among nonnegative-utility feasible sets. The empty baseline is always a valid comparison. A no-justified-set result can mean no benefit, rejected candidates, missing evidence or inadequate budgets; inspect exclusions to distinguish these cases.

Verify the selected subset with ablations and a fresh final holdout. No optimizer can certify unmeasured latency, out-of-distribution behavior, dynamic authorization or real-world reliability from invented gains.
