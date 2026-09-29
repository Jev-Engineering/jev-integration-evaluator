<div align="center">

# 🧠 Issue #49 — Safe synthetic history retention

**The first study in this series where the JEV arm passed its predeclared synthetic gates: better later-task recall under a hard token budget, with zero pin, byte, or provenance loss. Live adoption still needs real evidence.**

[![Issue](https://img.shields.io/badge/issue-%2349-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/49)
[![PR](https://img.shields.io/badge/PR-%2371-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/71)
[![Decision](https://img.shields.io/badge/decision-synthetic%20gates%20met%20%C2%B7%20live%20needs%20more%20evidence-yellow)](../validation/issue49-holdout-report.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20synthetic%20fixture-blueviolet)](#%EF%B8%8F-honest-limits)

*Candidate `JEV-594296255D6E` · 24 holdout cases · assignment seed 490146 · CompleteTech LLC*

</div>

---

## What was tested

`examples/coding-agent/agent.py::retain_history` is the historical count-budget comparator. `retention_study.py` compares it with a deterministic pinned-plus-recent policy and a bounded synthetic JEV item assessor, all behind a guarded host that accepts `/prune` only for **verbatim item retention**. `/compact` and invalid modes leave memory unchanged — generative compaction is a deliberately separate operation. The host checks immutable pins, item IDs and byte digests, provenance, revisions, exact token budgets, and a compare-and-swap fake-memory transaction with independent readback and rollback. **A model cannot change pins, mode, budget, or item text.**

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 8 calibration + 24 holdout cases: 20 `/prune` efficacy rows for all three arms, 4 mode-safety rows for guarded arms (the historical function has no mode argument and is N/A there) |
| ⚔️ **Arms** | `current` (count-budget `retain_history`), `deterministic` (pinned-plus-recent), `jev` (bounded synthetic item assessor) |
| 🏷️ **Labels** | `retention/` separates original histories, host-only fault injections, mode attacks, co-authored synthetic choices, reader-visible later questions, and scorer-only answers — neither chooser nor reader sees scorer answers or fault schedules |
| 🧑‍⚖️ **Review** | Independent semantic review (codex-rag45-independent) and code review (graph44), 2026-09-28 UTC, anchored by approved pre-metadata digests; the single holdout ran from the externally checked exact post-metadata digest |
| 📉 **Denominators** | Every blocked, missing, and failed outcome stays in its applicable denominator; reports contain IDs and counts, never original item text |

## 📊 Holdout results

### Efficacy (20 `/prune` rows)

| Arm | Later task success | Abstentions | Over-budget commits | Unresolved contradiction errors | Unnecessary retained tokens | Backend calls | Assessment calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current (count budget) | 8 / 20 | 0 | 2 | 2 | 15 | 20 | 0 |
| Deterministic pinned-plus-recent | 7 / 20 | 4 | 0 | 3 | 92 | 17 | 0 |
| JEV assessed | **12 / 20** | 7 | 0 | 0 | 137 | 14 | 65 |

**Paired effects:** JEV rescued 6 and regressed 2 versus current; rescued 5 and regressed 0 versus deterministic.

### Guarded safety (24 rows for guarded arms)

| Arm | Pin loss | Byte / provenance loss | Wrong-mode mutations | Needs review |
|---|---:|---:|---:|---:|
| Current | 3 | 0 | 0 | 0 |
| Deterministic | 0 | 0 | 0 | 0 |
| JEV | **0** | **0** | **0** | 2 |

The H23/H24 mode attacks were rejected by the host with zero assessments and zero backend writes. JEV's synthetic resource profile: 0.195 cost units, 18 ms per-call p95, 84 ms sequential per-episode p95 — all predeclared assumptions, with local runner wall time measured separately.

## ⚖️ Decision

> [!IMPORTANT]
> **Decision: `synthetic_gates_met_live_needs_more_evidence`.** The predeclared synthetic gate passed across both the efficacy and guarded-safety holdouts — the only such pass among the issue #44–#49 studies. But the report is explicit: `live_adoption: not_authorized_no_real_history_or_provider`. Passing a synthetic screen is the *entry ticket* to a real study, not a substitute for one.

> [!WARNING]
> **Adoption limit.** The choices and oracle were co-authored as synthetic fixtures and then independently reviewed. The visible task identified the anticipated domain, so this result does not establish arbitrary future recall, provider performance, live adoption, or permission to process real user history.

## ⚠️ Honest limits

- No user history, provider, production memory, or generator was used. Costs and latencies are preset synthetic assumptions.
- JEV retained **137** scorer-classified unnecessary tokens versus 92 deterministic and 15 current — its recall gain was not free.
- In H18, `fault_kind="keep"` records the raw proposed label, not the failure reason; its 45 ms late response became `uncertain` and still incurred the full 0.003 synthetic cost units.
- H07/H08 have no reviewed supersession edge; their single retained new-source answers do not show that dropping conflicting originals safely resolves contradictions in general.
- Tasks test anticipated-domain recall, not arbitrary future recall.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#71](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/71) |
| Signed head → merge | [`698c71d`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/698c71d) → [`82cc8c0`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/82cc8c0) |
| Frozen report | [`validation/issue49-holdout-report.json`](../validation/issue49-holdout-report.json) |
| Calibration harness check | [`validation/issue49-calibration-report.json`](../validation/issue49-calibration-report.json) |
| Study fixture | [`examples/coding-agent/retention/`](../examples/coding-agent/retention/) — design, reading notes, and rerun commands in the [coding-agent README](../examples/coding-agent/README.md) |
| Integrity | `source_base_commit` `bbd7730…` · study-spec SHA-256 `106d2e8…` · twelve input digests in the report's `input_sha256` |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
