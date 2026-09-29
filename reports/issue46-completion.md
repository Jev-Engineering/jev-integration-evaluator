<div align="center">

# ✅ Issue #46 — Independently observed task completion

**Does a bounded JEV completion assessment help a coding-agent loop stop at the right moment? On the 24-case frozen synthetic holdout it gained exactly zero verified completions over either comparator — and produced two false completions.**

[![Issue](https://img.shields.io/badge/issue-%2346-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/46)
[![PR](https://img.shields.io/badge/PR-%2369-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/69)
[![Decision](https://img.shields.io/badge/decision-disable__for__fixture-orange)](../validation/issue46-holdout-report.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20synthetic%20fixture-blueviolet)](#%EF%B8%8F-honest-limits)

*Candidate `JEV-CA6A0A259F69` · 24 holdout cases per arm · assignment seed 460149 · CompleteTech LLC*

</div>

---

## What was tested

`examples/coding-agent/agent.py::run_steps` historically trusts a success flag to decide an episode is done. `completion_study.py` compares that behavior against a deterministic completion check and a bounded synthetic JEV completion arm on fresh in-memory store clones. The host registers only `set_status` and `add_label`, checks exact arguments, task identity, permission, legal transitions and a three-attempt cap, and binds every scripted effect to the action, arguments, before-revision and raw-state digest. **The JEV label is advisory; it cannot issue an action or grant permission.**

An independent host observer captures before/after snapshots regardless of `result.success`, and a separate oracle (`completion_oracle.py`) reads raw checkpoints and receipts against a scorer-only file — catching unrequested mutations and continuation after the objective was already met.

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 8 calibration + 24 holdout cases in `examples/coding-agent/completion/`; all six arm orders occurred exactly four times |
| ⚔️ **Arms** | `current` (historical success flag), `deterministic` (host completion check), `jev` (bounded synthetic completion assessment) |
| 🧑‍⚖️ **Review** | Independent pre-result review recorded in the scorer metadata (graph44, 2026-09-28 UTC); the holdout CLI requires those fields and an externally checked exact study-spec digest |
| 🎭 **Adversarial cases** | H10 targets another task (rejected), H11 is permission-denied, H18 legally sets a goal-wrong status, H19 simulates an executor side effect and records a contract violation |
| 🔒 **Integrity** | Report binds `source_base_commit` `f9203f5…`, study-spec SHA-256 `c55d8de…`, and digests for all eight inputs |

## 📊 Holdout results

| Arm | Verified completion | False completion | Unnecessary continuation | Uncertain terminal | Unauthorized executor calls | Safety violations | Executor calls | Assessment calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current (success flag) | 12 / 24 | **9** | 9 | 0 | 2 | 1 | 50 | 0 |
| Deterministic check | 12 / 24 | 0 | 0 | 3 | 0 | 1 | 34 | 32 |
| JEV assessment | 12 / 24 | 2 | 0 | 5 | 0 | 1 | 34 | 32 |

Every arm kept all 24 episodes in its denominator, including the 12 failed episodes per arm. The JEV arm also recorded 2 invalid or failed assessments and 3 missing-or-timeout observations, with 0.064 synthetic cost units and synthetic assessment latency of 15 ms p50 / 25 ms p95.

## ⚖️ Decision

> [!IMPORTANT]
> **Predeclared decision: `disable_for_fixture`.** JEV's verified-completion gain was **0** against both current and deterministic arms, while it produced two false completions, one faulty-executor safety violation, and five uncertain terminal episodes. The deterministic check achieved the same 12/24 with zero false completions. Live adoption status: `needs_more_evidence_no_live_model_or_host_execution`.

The historical arm's nine false completions and two unauthorized fake-executor calls confirm the seam's ambiguity is real — but on this fixture, deterministic verification already captures the available benefit.

## ⚠️ Honest limits

- All calls and state are **synthetic**; no provider, production executor, or real agent was run.
- Costs and assessment latencies are preset synthetic assumptions. Local fixture runner wall time (6.6 ms total) is measured separately and is **not** an assessment-latency estimate.
- The calibration report ([`issue46-calibration-report.json`](../validation/issue46-calibration-report.json)) remains an offline harness check only.
- This result does not support live adoption or deployment; it disables the treatment **for this fixture**.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#69](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/69) |
| Signed head → merge | [`94c2e5b`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/94c2e5b) → [`bbd7730`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/bbd7730) |
| Frozen report | [`validation/issue46-holdout-report.json`](../validation/issue46-holdout-report.json) |
| Study fixture | [`examples/coding-agent/`](../examples/coding-agent/) — design and rerun commands in its [README](../examples/coding-agent/README.md) |
| Input digests | `input_sha256` in the report covers cases, assessments, oracle, policy, scorer, runner, schema, and source |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
