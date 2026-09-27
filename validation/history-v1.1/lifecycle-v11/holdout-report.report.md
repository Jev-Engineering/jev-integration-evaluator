# JEV held-out acceptance-gate validation

Evidence type: **synthetic**. Status: **synthetic_only**.

**This report never authorizes deployment.** Synthetic outcomes cannot qualify an integration for activation.

Frozen risk limit: 0.050000; familywise alpha: 0.050000.

| Check | Scheduled observations | Accepted | Errors | Coverage | Error upper bound | Pass |
|---|---:|---:|---:|---:|---:|---|
| Pooled | 120 | 120 | 0 | 1.000000 | 0.030273 | True |
| ordinary | 120 | 120 | 0 | 1.000000 | 0.030273 | True |

## Limits

Assumes independent, representative Bernoulli errors among accepted decisions.

Unique task/cluster IDs cannot prove statistical independence.

Do not reuse this holdout to choose another threshold, subgroup or rubric.

This validates the recorded acceptance gate, not the host's different inspection or fallback paths.

Distribution shift, adversarial security and source correctness are not certified.

Synthetic responses can exercise the computation but cannot justify activation.

Retain the frozen policy and report digests independently. Local files do not authenticate data collection, labels, or approval.

Report digest: `b9967ba72aeeb5d5a512d622b452e285207e5a94796446d04394774d724b8009`.
