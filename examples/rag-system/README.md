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

The committed [study report](study45-report.json) is the frozen fixture run.
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

`claim_check` remains the unchanged, disconnected seam for issue #47. No
combined passage and claim benefit is measured here.
