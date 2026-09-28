# rag-system

The historical `answer_request` forwards all retrieved chunks to an injected generator.
Issue #45 anchored the original symbol at commit
`ecb411b1df008df4eb55f24749f36218eac79b92` and symbol SHA-256
`ab4c308b8d9926d64584f04421bfae0861f62e20490d397baea1eba6ed6ca840`.
`answer_with_evidence` is an offline example of a host-owned passage decision
before generation. It accepts `Passage` records with stable `passage_id`,
`source_id`, `span`, `claim_id`, and an annotated `stance`. Its `EvidenceBundle`
keeps the original passage objects and maps citation IDs back to their source
spans. These annotations are synthetic source metadata, not verified facts.

The three registered policies are `current` (forward all), `lexical` (query
token overlap), and `jev` (one injected bounded assessment). The host rejects
unknown IDs/labels and malformed responses, returns `assessment_failed` on
timeout or assessor failure, and does not invoke the generator on failed or
insufficient evidence. For a selected claim, the host also retains retrieved
spans annotated as contradictory or uncertain. Generation is still a separate
injected action. Relevance and source annotations do not establish truth.

Run the fixed offline synthetic study from the repository root:

```shell
python examples/rag-system/run_study45.py --out path/to/new-report.json
python -m pytest -q tests/test_rag_evidence45.py
```

The committed [v1 study report](study45-report.json) is the first frozen fixture
run. It remains historical after review found that its resource limits and
failure cohort were incomplete.
`study45.json` fixes calibration cases C01–C02, untouched paired holdout cases
H01–H08, independent passage and answer expectations, fixture assessor labels,
rubric, seed, threshold, resource limits, and stop rule. The scorer alone reads
`gold`; neither the assessor nor the generator receives it. The fixture
generator selects the first annotated support span, includes any same-claim
contradiction, and otherwise abstains. The report records every scheduled case
and arm, passage decisions, selected IDs, citations, independent answer checks,
calls, source/data hashes, and local Python elapsed time. Model cost and model
latency are unknown. These small authored cases are a synthetic behavior check,
not an observed answer-quality study or evidence for activation.

On the eight holdout cases, the fixture checks passed in 4/8 current, 4/8
lexical, and 8/8 assessed runs. The assessed fixture made eight calls; the
other arms made none. All arms retained every material contradiction in these
cases. The assessor predictions were authored in the frozen study data and
are not a calibrated model or evidence that a provider would reproduce them.

The revised [v2 report](study45_v2_report.json) uses new, untouched holdout
IDs and three separately frozen files: [passage sets](study45_v2_cases.json),
[scorer-only labels](study45_v2_labels.json), and
[assessor predictions and policy](study45_v2_predictions.json). The runner
checks their reviewed SHA-256 digests before scoring. The labels are synthetic
author adjudications from the described registry, audit, and archive text;
they were reviewed before the run, but no independent human or real-world
fact check is claimed. The assessor and generator receive neither labels nor
the whole case record.

Run v2 from the repository root:

```shell
python examples/rag-system/run_study45_v2.py --out path/to/new-v2-report.json
python -m pytest -q tests/test_rag_evidence45_v2.py
```

The ten-case v2 holdout checked 7/10 current, 7/10 lexical, and 5/10 assessed
synthetic answers. The assessed arm retained five failed or missing outcomes
in its denominator, including scheduled missing, timeout, malformed reply,
simulated latency excess, and simulated cost excess. One material
contradiction was omitted after a timed-out assessment. It fails the preset
synthetic threshold, so the report explicitly rejects this fixture treatment.
Adoption is separately rejected because even a passing synthetic screen
would need independent observed task and provider evidence. Simulated model
cost and latency are separate from measured local Python elapsed time.

The original `claim_check` body remains unchanged. No combined passage and
claim benefit is measured here.

## Claim support fixture (#47)

The original `claim_check` helper still returns an injected classifier's raw
answer; it is not a delivery gate. `answer_with_claim_review` adds a separate
synthetic consumer. Its generator emits structured atomic claims with stable
claim IDs and citation references (`passage_id`, start, end, exact quote).
Before assessment, the host checks citation membership and verbatim spans in
the selected #45 `EvidenceBundle`. Passage stance is source metadata and does
not establish claim truth. Host request fields declare critical claims and
dependencies; neither model labels nor scorer labels can change them.

The consumer's registered policies are `deterministic` and `jev`. The latter
validates a complete per-claim `supported / contradicted / unsupported /
uncertain` assessment and evidence IDs. Code-owned rules release supported
claims, remove separable noncritical failed claims, block failed critical or
dependent claims, and request more evidence on uncertainty, cancellation,
malformed or missing assessment, timeout, or audit failure. An injected host
audit must succeed before a release or revision becomes a final answer. A late
result cannot resume a cancelled attempt. The example constructs no provider,
retrieval service, or production delivery mechanism.

The [frozen #47 case file](study47_cases.json), [scorer-only labels](study47_labels.json),
[synthetic predictions](study47_predictions.json), and [policy](study47_policy.json)
were independently reviewed before the holdout run. The
[report](study47_report.json) records all 15 holdout cases in four arms:
historical `answer_request` only, generic-classifier counterfactual (raw helper
output recorded but unused), deterministic span checks, and bounded assessed
consumer. Every arm gets the same retrieved passages with #45 assessment off.

```shell
python examples/rag-system/run_study47.py --out path/to/new-report.json
python -m pytest -q tests/test_rag_claim47.py tests/test_rag_claim47_study.py
```

The synthetic holdout passed independent final-answer checks in 7/15
historical, 7/15 generic counterfactual, 9/15 deterministic, and 9/15 assessed
cases. The assessed arm had five failed or missing assessments, one audit
failure, and one simulated resource breach. It fails the preset screen and
adoption is rejected from synthetic evidence. Assessor costs and latencies are
assigned fixture values; only local Python elapsed time was measured. This
study does not test a combined #45+#47 treatment or real answer quality.
