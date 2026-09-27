# Confidence, probability and calibration

The dated official TypeSafe documentation distinguishes three concepts. Choice returns a selected label, a distribution over supplied labels and a provider confidence statistic. Score returns a probability-weighted ordinal level, a level distribution/legend and provider confidence; a score is not automatically a probability of correctness. Noul returns a yes-probability and has no Choice-style confidence field.

The runtime validates finite ranges, exact question keys, candidate label membership, distributions summing to one, selected-label maximal probability, pinned model, usage metadata and Score consistency with its weighted levels. A malformed response abstains through the baseline path. No parser guarantee establishes semantic correctness.

Provider confidence is kept separate from selected-label probability and independent empirical correctness. An example threshold such as .90 does not prove 90% accuracy. For Noul, P(yes)=.99 says the criterion is likely true, not that the whole multi-question decision has .99 correctness. The secondary sufficient-evidence Noul is an additional semantic input, never a mathematical confidence certificate.

`calibrate` accepts homogeneous Choice or Noul records with a declared calibration/test split. It refuses mixed primitive, split, model, policy, rubric or subgroup cohorts; stratify them explicitly. Noul uses binary Brier/ECE on P(yes); Choice reports top-label Brier and multiclass sum-convention Brier, fixed-bin reliability and coverage/selective-risk curves. Confidence bins are diagnostic, not automatically probabilistic. Report bin counts, rare classes, subgroup reliability and sample uncertainty; ECE depends on binning and sample size.

`--select-threshold` uses Choice **calibration-split** rows, a minimum accepted count, and a pointwise Wilson upper error bound to select coverage. Adaptive threshold selection is not certified by the same sample. Freeze probability/confidence/evidence thresholds and validate the joint operational rule on an untouched test set. Independently justify stricter policy for irreversible or high-impact choices; do not silently replace those controls with a high number.

Active/canary mode requires an explicit receipt containing approved=true, calibration_validated=true, the pinned model, policy version, question hash, threshold hash and an actual held-out evidence reference. A changed question, model, policy or threshold invalidates that receipt. The receipt is host-controlled metadata, not a cryptographic authorization service and not proof against a dishonest editor. The agent may not fill approval booleans merely to unlock execution.

See `templates/activation-receipt.json` for a deliberately **unapproved** starting structure and `examples/run_demo.py` for an explicitly synthetic test-only receipt. Production receipts must never cite the synthetic demonstration as validation.
