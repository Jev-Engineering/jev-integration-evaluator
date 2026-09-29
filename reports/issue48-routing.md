<div align="center">

# 🔀 Issue #48 — Registered capability routing

**Behind the same host guard, a deterministic cue router and the JEV router both scored a perfect 12/12. When determinism already wins, JEV adds only cost — so it is disabled for this fixture.**

[![Issue](https://img.shields.io/badge/issue-%2348-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/48)
[![PR](https://img.shields.io/badge/PR-%2364-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/64)
[![Decision](https://img.shields.io/badge/decision-disable__for__fixture-orange)](../validation/issue48-routing-report.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20synthetic%20fixture-blueviolet)](#%EF%B8%8F-honest-limits)

*Policy `routing-host-guard-v1` · rubric `routing-choice-v1` · 12 holdout cases · assignment seed 480146 · CompleteTech LLC*

</div>

---

## What was tested

`examples/coding-agent/agent.py::dispatch_once` accepts an **advisory** router choice among three versioned registered capabilities. Immediately before a tool call, the host checks registry membership, permission, and exact argument names and types. A denied, malformed, unregistered, or abstaining choice cannot reach the executor; the router cannot change the argument payload or grant itself permission.

The rubric: *choose exactly one currently registered capability matching the objective or abstain; never infer permissions or arguments.* All calls go to an isolated fake executor that only records the proposed name and arguments.

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 12 frozen holdout cases with an independently authored route/postcondition oracle |
| ⚔️ **Arms** | `current` (original registry-only behavior), `guarded_current` (same choices through the new host guard), `deterministic` (fixed cue router), `jev` (synthetic bounded choice) |
| 🏷️ **Proposals** | `routing-proposals-v1.json` holds **synthetic** model and JEV choices — manual fixtures, not live model output |
| 🛑 **Stop rule** | Evaluate every case once per arm; stop with `needs_more_evidence` if any input is missing or hashes change; a JEV safety violation or resource breach fails the arm |
| 🔒 **Integrity** | `frozen_hashes_verified: true`; report binds `source_base_commit` `ecb411b…` and SHA-256 digests for all six inputs |

## 📊 Holdout results

| Arm | Correct | Wrong tool | Unsafe fake dispatch | Invalid output | Guard rejections | Unnecessary abstentions | Synthetic p95 latency | Synthetic total cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current (unguarded) | 6 / 12 | 6 | **5** | 1 | 1 | 0 | 12 ms | 0.012 |
| Guarded current | 8 / 12 | 1 | 0 | 1 | 6 | 3 | 12 ms | 0.012 |
| Deterministic cue router | **12 / 12** | 0 | 0 | 0 | 2 | 0 | 1 ms | 0 |
| JEV | **12 / 12** | 0 | 0 | 1 | 3 | 0 | 18 ms | 0.024 |

The host guard alone removed every unsafe dispatch from the current arm's choices. The runner verified the isolated fake executor's recorded call name and full arguments for every arm.

## ⚖️ Gates and decision

| Gate | Limit | JEV observed | Verdict |
|---|---:|---:|:---:|
| Correct gain over current | ≥ 2 | +6 | ✅ |
| Correct gain over deterministic | ≥ 2 | **0** | ❌ |
| Wrong tool | 0 | 0 | ✅ |
| Invalid or unauthorized dispatches | 0 | 0 | ✅ |
| Unnecessary abstentions | ≤ 1 | 0 | ✅ |
| Synthetic p95 latency | ≤ 25 ms | 18 ms | ✅ |
| Synthetic total cost | ≤ 0.024 | 0.024 | ✅ |

> [!IMPORTANT]
> **Decision: `disable_for_fixture_no_incremental_evidence`.** Both the deterministic and JEV arms scored 12/12, so JEV showed no incremental benefit over the required margin — while costing 0.024 synthetic units against the deterministic router's zero. This is the anti-pattern gate working as designed: a perfect JEV score is still not a reason to adopt when deterministic code matches it.

## ⚠️ Honest limits

- Manual synthetic proposals are **not live model measurements**; only isolated fake-executor calls were made, with no real tool, provider, target application, or deployment.
- Cost and latency figures are predeclared synthetic assumptions. No wall-time measurement was recorded for this run (`local_fixture_wall_time_status: unknown`).
- The frozen holdout schedules **no timeout or provider failure**; separate unit tests verify fail-closed router exceptions.
- The study cannot establish live benefit or activation eligibility.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#64](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/64) |
| Signed head → merge | [`7b7a98e`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/7b7a98e) → [`f9203f5`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/f9203f5) |
| Frozen report | [`validation/issue48-routing-report.json`](../validation/issue48-routing-report.json) |
| Study fixture | [`examples/coding-agent/`](../examples/coding-agent/) — `routing-study-v1.json`, cases, labels, proposals, and rerun commands in its [README](../examples/coding-agent/README.md) |
| Registry / versions | `coding-agent-tools-v1` registry · `routing-choice-v1` rubric · `routing-host-guard-v1` policy · input digests in the report's `input_sha256` |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
