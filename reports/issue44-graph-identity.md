<div align="center">

# 🕸️ Issue #44 — Graph entity identity

**Can a bounded JEV `same / related / different / uncertain` assessment gate entity merges better than the current classifier or plain deterministic rules? On this frozen synthetic holdout: no.**

[![Issue](https://img.shields.io/badge/issue-%2344-blue)](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/44)
[![PR](https://img.shields.io/badge/PR-%2362-informational)](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/62)
[![Decision](https://img.shields.io/badge/decision-reject-red)](../examples/graph-system/report.v1.json)
[![Evidence](https://img.shields.io/badge/evidence-offline%20frozen%20synthetic-blueviolet)](#%EF%B8%8F-honest-limits)

*Study `graph-identity-synthetic-v1` · 16 paired holdout cases · CompleteTech LLC*

</div>

---

## What was tested

`examples/graph-system/entities.py` is a small in-memory graph fixture whose atomic `merge_if_current` rechecks the expected revision, the exact candidate objects, and host approval under one lock before any merge. The question: should a JEV assessment (bounded to `same / related / different / uncertain`) advise that merge gate, replacing the current injected classifier — or should deterministic registration-ID rules stay in charge?

All three arms pass through the **same** host approval and revision gate. The classifier cannot approve, revise, or write; timeout, cancellation, provider exception, and malformed output fail closed without a merge. The original source candidate was `JEV-76A14AC85B1C`.

## Study design (frozen before the holdout)

| | |
|---|---|
| 🧪 **Split** | 4 calibration pairs (`c01`–`c04`), 16 untouched paired holdout cases (`h01`–`h16`) |
| ⚔️ **Arms** | `current` (recorded injected classifier), `deterministic` (registration-ID rules), `jev` (recorded bounded assessment) |
| 🏷️ **Labels** | `labels.v1.json` is scorer-only **declared synthetic truth**, frozen and reviewed before holdout execution |
| 💥 **Failure handling** | Injected timeout and malformed responses map to `uncertain` and count as failures — they stay in the denominator |
| 🔒 **Integrity** | The runner checks frozen SHA-256 digests of all six input files before scoring |

## 📊 Holdout results

| Arm | Scheduled | Wrong merges | Wilson 95% upper (wrong merge) | Missed eligible true merges | Abstentions | Injected failures | Simulated cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current injected classifier | 16 | 3 | 0.4301 | 2 / 7 | 2 | 0 | $0 |
| Deterministic rules | 16 | **0** | 0.1936 | 2 / 7 | 4 | 0 | $0 |
| JEV recorded assessment | 16 | 1 | 0.2833 | 2 / 7 | 4 | 2 | $0.008 |

Denied-approval and stale-revision cases remain in the schedule and produce no merge even when an arm answers `same`. Per-case records distinguish assessment error, host gate outcome, and mutation outcome.

## ⚖️ Gates and decision

The JEV arm failed **six** preset gates:

| Gate | Limit | JEV observed | Verdict |
|---|---:|---:|:---:|
| Wrong merges | 0 | 1 | ❌ |
| Wrong-merge Wilson 95% upper | ≤ 0.20 | 0.2833 | ❌ |
| Missed eligible true merges | ≤ 0.25 | 0.2857 | ❌ |
| Failures | 0 | 2 | ❌ |
| Missed-merge reduction vs. current | ≥ 1 | 0 | ❌ |
| Missed-merge reduction vs. deterministic | ≥ 1 | 0 | ❌ |
| Abstention fraction | ≤ 0.40 | 0.25 | ✅ |
| Simulated cost / latency | ≤ $0.01 · ≤ 50 ms | $0.008 · 10 ms | ✅ |

> [!IMPORTANT]
> **Decision: reject the JEV arm.** The deterministic rules made zero wrong merges at zero cost; the recorded JEV treatment made one wrong merge, added two failures, and improved nothing the gates measure. The Wilson bound describes uncertainty within this small synthetic schedule only — it is not a population safety guarantee.

## ⚠️ Honest limits

- Every model response is a **recorded synthetic replay**; no prompts, provider calls, production records, or graph-database writes occurred.
- The `$0.0005` and 10 ms per scheduled JEV case are **simulated** resource charges. Local wall time (measured) covers fixture operations only.
- Alias labels for `h02` and `h04` are declared synthetic truth, not independently verified identities.
- A real study would need external adjudicators, representative pairs, a real transaction contract and provenance requirements, source-matched adapter review, and observed cost and latency.

## 🔗 Provenance

| | |
|---|---|
| Pull request | [#62](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/62) |
| Signed head → merge | [`08b2a9f`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/08b2a9f) → [`4698c4b`](https://github.com/Jev-Engineering/jev-integration-evaluator/commit/4698c4b) |
| Frozen report | [`examples/graph-system/report.v1.json`](../examples/graph-system/report.v1.json) |
| Study fixture | [`examples/graph-system/`](../examples/graph-system/) — design, boundaries, and rerun commands in its [README](../examples/graph-system/README.md) |
| Input digests | Full SHA-256 digests for all six frozen inputs are recorded in `hashes_sha256` inside the report |

---

<div align="center">
<sub>🧭 <b>jev-integration-evaluator</b> · CompleteTech LLC · Evidence over assertion, always.</sub>
</div>
