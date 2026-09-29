# Reusable use-case template contracts v1 (issue #59 checkpoint)

This checkpoint records six distinct `use-case.<letter>@1.0.0` source contracts.
It is an offline source and
host-oracle inventory. It does not materialize, apply, install, start, configure,
or connect any of these use cases. The [machine-readable matrix](../jev_integration_evaluator/data/use-case-template-matrix-v1.json)
is versioned and pins the exact fixture bytes. `use_case_matrix()` reads it;
`inspect_use_case_source(root, id)` checks the current bytes without importing or
executing host code. The offline oracle test is
[`tests/test_reusable_templates.py`](../tests/test_reusable_templates.py).
The [finite console fixture](../examples/use-case-host/console.py) has a
separate direct-execution test in
[`tests/test_use_case_console_host.py`](../tests/test_use_case_console_host.py).
Its builder copies all five exact reviewed source modules into one regular
Python package with a declared `use-case-offline` console entry. One off-mode
command runs C, L, D, E, M and H consumers and writes six separate raw outcome
files plus a ready marker. The test reads those files independently and checks
the host's permission/dispatch, graph revision and merge receipt, contradictory
retrieval evidence, raw completion state, citation/audit disposition, and
retention readback. It also checks that an active-mode request creates no
effects. This is direct offline fixture execution; package build, installation,
supervised launch and use-case-specific template transforms remain pending.
Every new host requires a fresh source review and binding. The Python recipe
catalog's `implemented_bounded_shape` is a transform capability for a narrow
shape, not an installed use-case qualification.

| Case | Recipe and source contract | Offline oracle | Apply/install/launch/provider | Benefit |
| --- | --- | --- | --- | --- |
| C registered tool | `python.C@1.0`; [coding-agent dispatch](../examples/coding-agent/agent.py), [#48](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/48) | Existing registered-action and at-most-once dispatch tests; complete installed journey is [#57](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/57) | Pending | Unknown |
| L graph identity | `python.L@1.0`; [graph fixture](../examples/graph-system/entities.py), [#44](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/44) | Approval, exact entity snapshot, revision and audit before merge | Pending | Unknown |
| D retrieval evidence | `python.D@1.0`; [RAG fixture](../examples/rag-system/pipeline.py), [#45](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/45) | Passage provenance, missing evidence and material contradiction retention | Pending | Unknown |
| E completion | `python.E@1.0`; [raw-state oracle](../examples/coding-agent/completion_oracle.py), [#46](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/46) | Raw objective and effect receipts independent of executor success | Pending | Unknown |
| M claim support | `python.M@1.0`; [claim consumer](../examples/rag-system/pipeline.py), [#47](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/47) | Exact citation spans, critical-claim block, revision, audit before release | Pending | Unknown |
| H retention | `python.H@1.0`; [memory oracle](../examples/coding-agent/retention_oracle.py), [#49](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/49) | Pinned bytes/provenance, budget, mode and later recall | Pending | Unknown |

## Operator use and binding limits

For any row, run a read-only byte check from the checkout:

```python
from jev_integration_evaluator.use_case_templates import use_case_matrix, inspect_use_case_source
rows = use_case_matrix()["rows"]
source_status = inspect_use_case_source("/reviewed/source/root", "L")
```

`source_matched` means only that the inspected file equals the pinned fixture
bytes. It does not prove a target binding, implementation, installed entrypoint,
provider response, or adoption result. A mismatch requires renewed review;
there is no automatic adaptation or rollback. Keep source and output private.
Use the existing `template validate`, `template bind`, `implement-plan`, and
separately approved lifecycle commands only after a *new* host review produces
the exact inventory/spec, policy, source grammar, and host-owned interfaces.
The five fixture consumers are currently outside the automatic
`module-tail-call-v1` grammar. No generated patch for them is claimed here.
After #56 is merged, the finite console host can be carried through the
separate #54 source verification, #55 package/install and #56 delivery receipt
contracts. #56 requires an externally retained install receipt digest and
independent ready, entrypoint and integration observations. Those observations
must check the six raw outcome files under an approved off-mode launch, with
the explicit `/prune` choice and a separate `/compact` no-mutation check.

### L: graph identity

Bind two provenance-bearing entities, a host-owned approval, the expected graph
revision, an atomic merge adapter and durable pre-mutation audit. An assessment
may propose `same`, `related`, `different`, or `uncertain`; only exact `same`
with approval and a current revision may merge. A stale revision, changed entity,
missing approval, malformed assessment or failed audit leaves the graph intact.
The in-memory fixture is not a graph database transaction. A real host needs its
own atomic transaction proof and rollback ownership.

### D: retrieval evidence

Bind a query, stable passage/source/span/claim IDs, stance metadata, retriever,
and generation consumer. Missing evidence does not generate an answer. A
contradictory passage for a selected material claim remains in the evidence
bundle even when its initial relevance label is negative. Stance is metadata,
not a truth label; the separate generator and independent answer evaluation
remain necessary. Unsupported: missing provenance, ambiguous IDs, or a target
without the reviewed handoff seam.

### E: completion

Bind a finite objective, legal actions, independently read raw state and effect
receipts, and a bounded step owner. `result.success` cannot certify completion.
The fixture's `exact_goal` and `score_trace` check final state and each scheduled
checkpoint; partial, stale, or unrecorded effects fail. A real host must supply
its own raw observer and action/retry authority. No extra action or attempt is
authorized by an assessment.

### M: claim disposition

Bind atomic claims, critical IDs, exact passage IDs/spans/quotes, a host release
policy and durable audit. Invalid critical citations block; invalid noncritical
claims can be removed only under the explicit dependency policy. Uncertain
assessments request more evidence. The answer is released only after host audit.
Missing, fabricated or partly valid citations do not become supported by model
labels. D's passage selection and M's claim disposition are separate consumers
and experiments.

### H: safe retention

Bind immutable pinned items, byte/provenance digests, a token budget, explicit
user mode and later-recall questions. `/prune` may select existing intact items
only after host pin/budget checks; `/compact` is a separate generative policy and
is **not** performed by this contract. Changing retained raw bytes, dropping a
pin, committing over budget, or mutating under `/compact` fails the raw oracle.
Later recall is scored separately, with missing results counted as failure.
No user history is processed here.

## Whole-catalog support boundary

Python recipes A, B, C, D, E, F, G, H, I, J, K, L and M remain catalogued at
version 1.0 for the narrow `module-tail-call-v1` transform. For each of A, B,
F, G, I, J and K, use-case-specific source contract, installed execution,
connected mode and benefit are **not qualified by this checkpoint**. For C, L,
D, E, M and H, the matrix records only the corresponding source/oracle state;
all installed and connected cells remain pending. The separate JavaScript/TypeScript
`javascript.C@1.0` flat async backend has its own source catalog; it has no
L/D/E/M/H coverage and no installed Node journey from this checkpoint. All
rows remain mode **off**. Shadow, canary and active require separate authenticated
authority and their own evidence. Experiments #44–#49 retain independent
comparators and adoption decisions.
