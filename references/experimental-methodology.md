# Experimental methodology

## Freeze the causal question

Specify the exact insertion point, independently verified outcome, target task distribution and minimum useful effect before modifying behavior. Freeze source/model/rubric/policy versions, task hashes, assignment unit, random seeds, calibration split, untouched holdout, labels, failure taxonomy, safety/resource limits and stop rule. Register a fixed sample size or a valid sequential design; do not repeatedly peek and stop at an attractive p-value. The default 30 independent clusters is a screening floor, not a statistical power guarantee.

Prefer matched tasks or independently reset episodes under baseline and treatment; counterbalance run order and isolate mutable state. Retain all scheduled failures, timeouts and malformed outputs. `compare` refuses missing pairs, duplicate task/replicate keys, mixed treatments/versions, seed/hash mismatches, shadow/predicted outcomes and different evaluation scopes. Replicates within a task or explicit cluster are not independent observations.

## What each evidence mode establishes

Offline decision replay with independently labeled states measures bounded decision accuracy, not the unobserved future after an alternative action. An unlabeled disagreement is not a rescue. Shadow mode leaves baseline control unchanged and measures proposals, agreement, resource use and failures. It cannot observe how the unexecuted action would have changed the task. Canary exposes a small stable task cohort under host approval and deterministic rollback conditions; unpaired observational canary data must not be fabricated into matched pairs.

Synthetic fixtures test the tooling and are labeled synthetic throughout. They always remain needs_more_evidence for adoption. A completed randomized or properly paired task/episode run can support task success claims, subject to its design and uncertainty. Correlated model judges, leaked examples and subjective labels can invalidate a seemingly precise result; use independent observable postconditions and blinded adjudication where possible.

## Paired outcomes and uncertainty

Count both-pass, both-fail, baseline-fail/JEV-pass rescues and baseline-pass/JEV-fail regressions. Absolute improvement is the paired success-rate difference. Relative improvement is null when the baseline rate is zero. Rescue/regression ratio is null with an explicit infinite/no-discordance status when the denominator is zero; it is not a magical certainty statement.

Independent binary pairs use the exact two-sided conditional-binomial McNemar test. Clustered/repeated pairs withhold ordinary McNemar. The package uses reproducible paired cluster percentile bootstrap confidence intervals, preserving pair structure and resampling independent clusters. The estimand is the task-weighted mean, not equal-weighted per-cluster means. Small clusters or no variation produce explicit warnings. These are percentile intervals, not BCa; they cannot reveal unobserved failure modes.

For independent pairs, Bayesian inference uses the joint four-cell multinomial with a symmetric Dirichlet(0.5, 0.5, 0.5, 0.5) prior. It estimates P(delta > 0) and P(delta > the minimum useful effect), rather than independently fitting two marginal Bernoulli rates and discarding pairing. Repeated clusters use a cluster Bayesian bootstrap with Dirichlet(1,...,1) weights on observed clusters. Report prior/support assumptions, Monte Carlo sample count/error, and sensitivity to task/subgroup choice.

Continuous metric results include paired mean delta, standardized paired effect dz where nonzero variance exists, and bootstrap uncertainty. Latency includes p50, p95, p95 difference and the p95 of paired added latency; the latter is used against the configured added-latency ceiling. These are different estimands and should not be interchanged. Incomplete metric cohorts are disclosed and cannot satisfy full operational validation.

## Multi-objective usefulness

Track quality, verified completion, failures, tokens, model and tool calls, latency, cost, retries, human escalations, prevented unsafe actions, actual unsafe actions, false blocks, replans and verified progress. Record ground truth for an allegedly prevented unsafe action rather than counting every refusal as a safety win. Compare successful tasks and verified progress per call/token/cost/time. Ratio-of-totals denominators include failed tasks.

Pareto dominance uses declared max/min directions on measured point estimates. It is not an uncertainty-aware dominance proof. An apparent quality gain may trade against p95 latency, cost, false blocks, maintainability or safety; do not collapse these tradeoffs into accuracy alone.

Run no-JEV, router-only, verifier-only and router+verifier arms, then add justified recovery/context ablations. The ablation tool applies Holm adjustment to available exploratory McNemar p-values and reports the router/verifier difference-in-differences interaction with clustered bootstrap uncertainty. Use a final untouched holdout after choosing a variant; post-selection reuse of the tuning set overstates evidence.

Track baseline failure class → treatment failure class, including pass. A routing failure becoming a state-tracking failure is movement, not a rescue. Expand the default taxonomy for the repository and predeclare labels. Classify eliminated, reduced, moved or worsened failures from the actual transition counts.

Engineering economics computes per-task avoided failure cost, added inference/maintenance cost, net value and break-even fixed setup volume. Use owner-provided costs and dated prices; unknown pricing is not zero. Do not double-count reduced model calls both as additional savings and a net inference-cost measurement. Test cost/failure uncertainty and realistic volume sensitivity before an adoption decision.

For long horizons, p^n is only the equal-probability independent-step approximation. The tool labels the assumption and also reports dependence bounds using the common marginal p. Real agents may have correlated failures, recovery, policy changes and nonstationarity; measure full episodes rather than claiming p^n proves reliability.

## Dispositions and stop criteria

Disable on observed safety harm, resource excess or success intervals below zero. A keep disposition requires sufficient independent clusters, the useful-effect interval/posterior gates, complete operational metrics, no increased false blocks, validated calibration and observed task-level—not decision-only or synthetic—evidence. Otherwise modify or collect more evidence. Keep is a research disposition, never authority to deploy.

Immediate canary rollback conditions are separately supplied deterministic limits on unsafe actions, failure rate, paired/appropriately measured p95 added latency, mean added cost and fallback rate. False-block thresholds should be tracked as a host-specific additional stop rule. The tool never auto-expands traffic. A correct conclusion may be that JEV provides insufficient value and should be removed.
