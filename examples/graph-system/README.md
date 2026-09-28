# Offline graph entity identity experiment (issue #44)

`entities.py` is a deliberately small in-memory graph fixture. Its atomic
`merge_if_current` method rechecks the expected revision, checks the exact
candidate objects, increments the revision, and records both source names under
one lock. An optional host audit callback runs inside that lock **before** the
fixture appends a merge receipt or increments the revision. An audit exception
leaves the graph unmodified. The fixture has no durable external audit service;
the callback contract does not establish atomicity with such a service.
`reconcile` accepts only the exact `same` label and explicit host approval.
Classifier timeout, cancellation, provider exception, and malformed output
fail closed without a merge. The classifier cannot approve, revise, or write. This is a transaction
analogue for the fixture, not a connected database transaction or production
identity policy. The original source candidate was `JEV-76A14AC85B1C`, symbol
SHA-256 `85f8600662bd618ae47cc88401d8c77a926361e2bd3c039d09ea48cb37d408f3`.
This experiment does not use the unsupported automatic Python recipe for that
function.

## Frozen design and boundaries

The four calibration pairs are `c01`–`c04`; the untouched paired holdout is
`h01`–`h16`. Each arm sees the same public pair fields (`name`, `jurisdiction`,
`registry_id`, source provenance) in a fresh graph. `labels.v1.json` is a
separate, scorer-only synthetic adjudication file. The alias labels for `h02`
and `h04` are **declared synthetic truth**, not independently verified real
identities or evidence available to an assessor. The label and response files
were frozen before holdout execution and reviewed separately. They are
illustrative recorded decisions, not measured model output. There are no
prompts, provider calls, production records, or graph database writes.

The current arm replays a recorded injected classifier. The deterministic arm
uses equal nonempty registration IDs in the same jurisdiction for `same`,
conflicting IDs or jurisdictions for `different`, and otherwise abstains. The
JEV arm replays recorded bounded `same / related / different / uncertain`
answers. Injected timeout and malformed responses raise fixture exceptions,
map to `uncertain`, and count as failures. All three arms pass through the same host approval and revision
gate. The inputs, rules, thresholds, resource model, and stop rule are in
`study.v1.json`. The runner checks frozen SHA-256 digests before scoring.

Run from the repository root:

```shell
python examples/graph-system/run_experiment.py --out examples/graph-system/report.v1.json
python -m pytest -q tests/test_graph_identity_experiment.py
```

The first command writes a paired case report with source/data hashes. Local
wall time is measured for fixture operations only; `$0.0005` and 10 ms per
scheduled JEV case are **simulated** resource charges, not observed provider
cost or latency. Zero-cost comparator values are likewise simulation inputs.

## Frozen holdout result

| Arm | Scheduled | Wrong merges | Missed eligible true merges | Abstentions | Injected failures | Simulated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current injected classifier | 16 | 3 | 2 / 7 | 2 | 0 | $0 |
| Deterministic rules | 16 | 0 | 2 / 7 | 4 | 0 | $0 |
| JEV recorded assessment | 16 | 1 | 2 / 7 | 4 | 2 | $0.008 |

**Decision: reject this recorded JEV treatment.** It fails the preset zero
wrong-merge gate, the missed-merge gate, the zero-failure gate, and the
minimum improvement over both baselines. The 95% Wilson upper bound for the
wrong-merge event is 0.2833 for JEV (1 event / all 16 scheduled pairs), above
the preset 0.20 limit. The Wilson interval describes uncertainty within this
small synthetic schedule; it is not a population safety guarantee. Denied
approval and stale revision cases remain in the schedule and produce no merge,
even when an arm says `same`. The runner records every scheduled case, including
both injected failures. The report's per-case records distinguish assessment
error, host gate outcome, and mutation outcome.

This result does not measure a live JEV model, establish false-merge prevalence,
or authorize deployment. A real study would need external adjudicators,
representative pairs, a real transaction contract and provenance requirements,
source-matched adapter review, and observed cost and latency.
