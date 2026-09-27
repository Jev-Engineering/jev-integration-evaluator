# JEV held-out acceptance-gate validation

Evidence type: **synthetic**. Status: **synthetic_only**.

**This report never authorizes deployment.** Synthetic outcomes cannot qualify an integration for activation.

Frozen risk limit: 0.050000; familywise alpha: 0.025000.

| Check | Scheduled observations | Accepted | Errors | Coverage | Error upper bound | Pass |
|---|---:|---:|---:|---:|---:|---|
| Pooled | 120 | 120 | 0 | 1.000000 | 0.035858 | True |
| ordinary | 120 | 120 | 0 | 1.000000 | 0.035858 | True |

## Limits

Assumes independent, representative Bernoulli errors among accepted decisions.

Unique task/cluster IDs cannot prove statistical independence.

Do not reuse this holdout to choose another threshold, subgroup or rubric.

This validates the recorded acceptance gate, not the host's different inspection or fallback paths.

Distribution shift, adversarial security and source correctness are not certified.

Synthetic responses can exercise the computation but cannot justify activation.

Retain the frozen policy and report digests independently. Local files do not authenticate data collection, labels, or approval.

Report digest: `9ab727ea84a04ae2d0bad19a9779ab53baaaa07f747fe5aaacab5fe642c32373`.
