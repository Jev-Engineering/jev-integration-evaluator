# JEV canary operational window

Status: **guardrail_breach**. Recommendation: **suspend**.

Evidence: synthetic. Scheduled: 80; received: 80; missing: 0; incomplete: 0.

No exposure expansion or deployment is authorized by this report.

| Cohort | Complete | Breached guardrails |
|---|---|---|
| Pooled | True | unsafe_actions |
| ordinary | True | unsafe_actions |

## Interpretation limits

Metrics are operational point summaries, not statistical significance or causal estimates.

Empirical p95 uses nearest rank; the latency difference is between arm quantiles, not a paired latency quantile.

No optional-stopping or repeated-window probability guarantee is claimed.

Missing outcomes and unknown costs cannot silently pass monitoring.

Frozen reference action drift is descriptive and does not alone establish model quality degradation.

Assignment IDs, observed labels and local timestamps need independently trusted provenance.

A healthy window does not prove overall safety or authorize a larger canary.
