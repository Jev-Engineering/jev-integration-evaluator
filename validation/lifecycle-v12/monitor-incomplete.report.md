# JEV canary operational window

Status: **incomplete_overdue_window**. Recommendation: **suspend**.

Evidence: synthetic. Scheduled: 80; received: 79; missing: 1; incomplete: 1.

No exposure expansion or deployment is authorized by this report.

| Cohort | Complete | Breached guardrails |
|---|---|---|
| Pooled | False | None observed |
| ordinary | False | None observed |

## Interpretation limits

Metrics are operational point summaries, not statistical significance or causal estimates.

Empirical p95 uses nearest rank; the latency difference is between arm quantiles, not a paired latency quantile.

No optional-stopping or repeated-window probability guarantee is claimed.

Missing outcomes and unknown costs cannot silently pass monitoring.

Frozen reference action drift is descriptive and does not alone establish model quality degradation.

Assignment IDs, observed labels and local timestamps need independently trusted provenance.

A healthy window does not prove overall safety or authorize a larger canary.
