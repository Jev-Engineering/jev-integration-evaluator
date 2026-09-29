<div align="center">

# 📚 Issue #45 — RAG evidence selection

**Should a bounded JEV passage assessment decide which retrieved evidence reaches the generator? The v2 frozen synthetic holdout says no — the assessed arm scored *worse* than simple lexical overlap.**

[![Issue](https://img.shields.io/badge/issue-%2345-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/45)
[![PR](https://img.shields.io/badge/PR-%2365-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/65)
[![Decision](https://img.shields.io/badge/decision-reject-red)](../examples/rag-system/study45_v2_report.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20synthetic%20fixture-blueviolet)](#%EF%B8%8F-honest-limits)

*Study `rag-evidence-45-v2` · seed 4502 · 10 new holdout cases · CompleteTech LLC*

</div>

---

## What was tested

The historical `answer_request` in `examples/rag-system/pipeline.py` forwards **all** retrieved chunks to an injected generator. `answer_with_evidence` is an offline example of a host-owned passage decision before generation: the host rejects unknown IDs and labels, fails closed on timeout or assessor failure, and never invokes the generator on failed or insufficient evidence. For a selected claim it also retains retrieved spans annotated as contradictory or uncertain.

This v2 study replaced the historical v1 run after review found v1's resource limits and failure cohort incomplete. The v1 report remains historical.

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 2 calibration cases (`V2-C01`–`V2-C02`), 10 **new** untouched holdout cases (`V2-H01`–`V2-H10`) |
| ⚔️ **Arms** | `current` (forward all), `lexical` (query token overlap), `jev` (one injected bounded assessment per case) |
| 🏷️ **Labels** | Scorer-only expected passage and answer identities, predeclared by the case author and frozen separately from assessor responses |
| 📏 **Limits** | ≤ 1 assessor call and ≤ 1 generator call per case, ≤ 32 retrieved passages, ≤ $0.001 simulated assessor cost and ≤ 100 ms simulated latency per case |
| 🛑 **Stop rule** | Run each holdout case once under all three arms in fixed order; never stop early or tune from holdout; every failure stays in the denominator |

## 📊 Holdout results

| Arm | n | Answer success | Failed or missing | Contradiction omissions | Cost-limit violations | Latency-limit violations | Assessor calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current (forward all) | 10 | 7 | 0 | 0 | 0 | 0 | 0 |
| Lexical overlap | 10 | 7 | 0 | 0 | 0 | 0 | 0 |
| JEV assessed | 10 | **5** | **5** | 1 | 1 | 1 | 10 |

The assessed arm kept all five failed or missing outcomes in its denominator — scheduled missing, timeout, malformed reply, simulated latency excess, and simulated cost excess. One material contradiction was omitted after a timed-out assessment.

## ⚖️ Gates and decision

| Gate | Limit | JEV observed | Verdict |
|---|---:|---:|:---:|
| Answer-success gain over lexical | ≥ +0.2 | **−0.2** | ❌ |
| Missing or failed outcomes | 0 | 5 | ❌ |
| Contradiction omissions | 0 | 1 | ❌ |
| Cost-limit violations | 0 | 1 | ❌ |
| Latency-limit violations | 0 | 1 | ❌ |

> [!IMPORTANT]
> **Screen decision: `reject_on_frozen_synthetic_threshold`. Adoption decision: `reject_adoption_from_synthetic_evidence`.** The fixture treatment fails on both effectiveness and every failure/resource gate. Even a passing synthetic screen would still have required independent observed task and provider evidence (`next_evidence: needs_independent_real_task_and_provider_observation`).

## ⚠️ Honest limits

- Fixture predictions, costs, and latency are **authored simulations**; local elapsed time is Python runtime only. No provider, real retrieval, real answer quality, model cost, or model latency was measured.
- Labels are the synthetic case author's predeclared expectations — scorer-only, with no independent adjudication panel.
- The original `claim_check` body is unchanged, and no combined #45 + #47 treatment was measured here.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#65](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/65) |
| Signed head → merge | [`10cd1d2`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/10cd1d2) → [`6babaf0`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/6babaf0) |
| Frozen report | [`examples/rag-system/study45_v2_report.json`](../examples/rag-system/study45_v2_report.json) |
| Frozen inputs | [Passage sets](../examples/rag-system/study45_v2_cases.json) · [scorer-only labels](../examples/rag-system/study45_v2_labels.json) · [predictions and policy](../examples/rag-system/study45_v2_predictions.json) — full SHA-256 digests in the report's `source_sha256` |
| Historical v1 | [`study45-report.json`](../examples/rag-system/study45-report.json) — superseded, retained for the record |
| Fixture and rerun commands | [`examples/rag-system/README.md`](../examples/rag-system/README.md) |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
