<div align="center">

# 🔍 Issue #47 — RAG claim checking

**Can a bounded per-claim JEV assessment (`supported / contradicted / unsupported / uncertain`) make final answers safer than deterministic span checks? It eliminated unsafe claims — but blocked six supported ones and failed five assessments, so the frozen synthetic screen rejects it.**

[![Issue](https://img.shields.io/badge/issue-%2347-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/47)
[![PR](https://img.shields.io/badge/PR-%2367-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/67)
[![Decision](https://img.shields.io/badge/decision-reject-red)](../examples/rag-system/study47_report.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20synthetic%20fixture-blueviolet)](#%EF%B8%8F-honest-limits)

*Study `rag-claim-47-v1` · seed 4701 · 15 holdout cases × 4 arms · CompleteTech LLC*

</div>

---

## What was tested

The original `claim_check` helper in `examples/rag-system/pipeline.py` returns an injected classifier's raw answer — it is not a delivery gate. `answer_with_claim_review` adds a separate synthetic consumer: the generator emits structured atomic claims with stable IDs and citation references, the host verifies citation membership and verbatim spans in the selected #45 `EvidenceBundle`, and **code-owned rules** decide disposition — release supported claims, remove separable noncritical failures, block failed critical or dependent claims, and request more evidence on uncertainty, cancellation, malformed or missing assessment, timeout, or audit failure. An injected host audit must succeed before any release becomes a final answer; a late result cannot resume a cancelled attempt.

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 2 calibration cases (`C01`–`C02`), 15 untouched holdout cases (`H01`–`H15`), all four arms per case, fixed order |
| ⚔️ **Arms** | `historical` (`answer_request` only), `generic_classifier_counterfactual` (raw helper output recorded but unused), `deterministic` (span checks), `jev` (bounded assessed consumer) |
| 🏷️ **Labels** | Scorer-only claim adjudication frozen before the holdout; case, prediction, and label files independently reviewed before the run |
| 📏 **Limits** | ≤ 1 assessor and ≤ 1 generator call per case, ≤ 4 claims, ≤ 3 citations per claim, ≤ 32 passages, ≤ $0.001 simulated cost and ≤ 100 ms simulated latency per case |
| 🛑 **Stop rule** | No early stop, no post-result tuning; every scheduled failure stays in the denominator; a synthetic pass never authorizes adoption |

## 📊 Holdout results

| Arm | Answer success | Unsafe claims delivered | Material conflict omissions | Supported claims blocked | Failed / missing assessments | Audit failures | Resource violations |
|---|---:|---:|---:|---:|---:|---:|---:|
| Historical | 7 / 15 | 8 | 2 | 0 | 0 | 0 | 0 |
| Generic classifier (counterfactual) | 7 / 15 | 8 | 2 | 0 | 0 | 0 | 0 |
| Deterministic span checks | 9 / 15 | 6 | 2 | 0 | 0 | 0 | 0 |
| JEV assessed consumer | 9 / 15 | **0** | **0** | **6** | **5** | 1 | 1 |

The assessed arm was the only one to deliver zero unsafe claims and omit zero material conflicts — but it paid for that by blocking six supported claims and failing or missing five assessments.

## ⚖️ Gates and decision

| Gate (minimum useful effect) | Limit | JEV observed | Verdict |
|---|---:|---:|:---:|
| Answer-success gain over deterministic | ≥ +0.2 | **0.0** | ❌ |
| Additional supported claims blocked | 0 | 6 | ❌ |
| Failed or missing assessments | 0 | 5 | ❌ |
| Audit failures | 0 | 1 | ❌ |
| Resource violations | 0 | 1 | ❌ |
| Unsafe claims delivered | 0 | 0 | ✅ |
| Material conflict omissions | 0 | 0 | ✅ |

> [!IMPORTANT]
> **Screen decision: `reject_on_frozen_synthetic_threshold`. Adoption decision: `reject_adoption_from_synthetic_evidence`.** The safety wins were real within the fixture, but the predeclared screen requires them *without* new false blocks, assessment failures, audit failures, or resource breaches — and with a measurable answer-success gain. It delivered none of that margin.

## ⚠️ Honest limits

- Small authored corpus; **no real retrieval, model, provider cost/latency, user history, or deployment** was involved. Only local Python elapsed time was measured; assessor costs and latencies are assigned fixture values.
- Passage stance is source metadata and does not establish claim truth; scorer labels are the synthetic author's pre-holdout adjudication.
- No combined #45 + #47 treatment was tested — the two placements' interaction remains unmeasured.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#67](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/67) |
| Signed head → merge | [`96b8851`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/96b8851) → [`4f78a9c`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/4f78a9c) |
| Frozen report | [`examples/rag-system/study47_report.json`](../examples/rag-system/study47_report.json) |
| Frozen inputs | [Cases](../examples/rag-system/study47_cases.json) · [scorer-only labels](../examples/rag-system/study47_labels.json) · [predictions](../examples/rag-system/study47_predictions.json) · [policy](../examples/rag-system/study47_policy.json) — full SHA-256 digests in the report's `source_sha256` |
| Fixture and rerun commands | [`examples/rag-system/README.md`](../examples/rag-system/README.md) |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
