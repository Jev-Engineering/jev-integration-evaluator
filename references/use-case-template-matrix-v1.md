# Reusable use-case template contracts v1 (issue #59 checkpoint)

This checkpoint records six distinct `use-case.<letter>@1.0.0` source contracts.
It is an offline source and host-oracle inventory with separately qualified
offline L, D, E and H synthetic hosts. It does not connect any provider. The
[machine-readable matrix](../jev_integration_evaluator/data/use-case-template-matrix-v1.json)
is versioned and pins the exact fixture bytes. `use_case_matrix()` reads it;
`inspect_use_case_source(root, id)` checks the current bytes without importing or
executing host code. The offline oracle test is
[`tests/test_reusable_templates.py`](../tests/test_reusable_templates.py).
The [finite console fixture](../examples/use-case-host/console.py) has a
separate direct-execution test in
[`tests/test_use_case_console_host.py`](../tests/test_use_case_console_host.py).
Its builder checks the matrix-pinned console and project bytes, then copies
those and all five exact reviewed source modules into one regular Python
package with a declared `use-case-offline` console entry. One off-mode
command runs C, L, D, E, M and H consumers and writes six separate
fixture-emitted outcome records plus a ready marker in fresh paths. The fixture
requires owner-only `0700` directories on POSIX; native Windows ACL ownership
is not qualified by this direct-execution check.
The test reads those files after process exit and checks
the host's permission/dispatch, graph revision and merge receipt, contradictory
retrieval evidence, raw completion state, citation/audit disposition, and
retention readback. It also checks that an active-mode request creates no
effects. The files are authored by the same fixture process that runs the
consumers; they are not independent observations of external effects. The
[installed fixture test](../tests/test_use_case_installed_console.py) additionally
checks the copied source and exact module bytes inside an offline-built wheel,
installs that wheel in a fresh Linux CPython 3.13 environment, invokes the
declared `use-case-offline` command with runtime mode `off`, checks the six
fixture-emitted records, rejects an active-mode launch before effects, and
uninstalls the package. This proves normal installed invocation of the shared
fixture host only. It does not provide a #54 implementation receipt, #55
source-bound package/install receipt, #56 supervised session, independent raw
effect observation, or any individual L/D/E/M/H template transform. The
separate L, D, E and H journeys below have their own #55/#56 receipts and raw effects;
neither is inferred from this shared fixture.
Every new host requires a fresh source review and binding. The Python recipe
catalog's `implemented_bounded_shape` is a transform capability for a narrow
shape, not an installed use-case qualification.

| Case | Recipe and source contract | Offline oracle | Apply/install/launch/provider | Benefit |
| --- | --- | --- | --- | --- |
| C registered tool | `python.C@1.0`; [coding-agent dispatch](../examples/coding-agent/agent.py), [#48](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/48) | Existing registered-action and at-most-once dispatch tests; complete installed journey is [#57](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/57) | Pending | Unknown |
| L graph identity | `python.L@1.0`; [graph fixture](../examples/graph-system/entities.py) and [pinned consumer](../examples/use-case-host/graph_runtime.py), [#44](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/44) | Approval, exact entity snapshot, revision and audit before merge | Offline synthetic L host: source-bound plan/apply/verify, #55 install, #56 normal-console observation/disable/versioned upgrade/generation rollback; #54 L bind and provider pending | Unknown |
| D retrieval evidence | `python.D@1.0`; [RAG fixture](../examples/rag-system/pipeline.py), [pinned corpus](../examples/use-case-host/retrieval_corpus_v1.json) and [consumer](../examples/use-case-host/retrieval_consumer.py), [#45](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/45) | Passage provenance, missing evidence and material contradiction retention | Offline synthetic D host: source-bound plan/apply/verify, #55 install, #56 normal-console observation/disable/versioned upgrade/generation rollback; #54 D bind and provider pending | Unknown |
| E completion | `python.E@1.0`; [raw-state oracle](../examples/coding-agent/completion_oracle.py), [#46](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/46) | Raw objective and effect receipts independent of executor success | Offline synthetic E host: source-bound plan/apply/verify, #55 install, #56 normal-console observation/disable/versioned upgrade/generation rollback; #54 E console bind and provider pending | Unknown |
| M claim support | `python.M@1.0`; [claim consumer](../examples/rag-system/pipeline.py), [#47](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/47) | Exact citation spans, critical-claim block, revision, audit before release | Pending | Unknown |
| H retention | `python.H@1.0`; [memory oracle](../examples/coding-agent/retention_oracle.py) and [consumer adapter](../examples/use-case-host/retention_consumer.py), [#49](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/49) | Raw retained-item bytes, pinned provenance, budget and explicit `/prune` | Offline synthetic H host: source-bound plan/apply/verify, #55 install, #56 normal-console observation/disable/versioned upgrade/generation rollback; #54 H console bind and provider pending | Unknown |

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
The finite console host still needs to be carried through the separate #54
source verification, #55 package/install and #56 delivery receipt
contracts. #56 requires an externally retained install receipt digest and
independent ready, entrypoint and integration observations. Those observations
must check the six fixture-emitted outcome files against independent host
postconditions under an approved off-mode launch, with
the explicit `/prune` choice and a separate `/compact` no-mutation check.

### L: graph identity

Bind two provenance-bearing entities, a host-owned approval, the expected graph
revision, an atomic merge adapter and durable pre-mutation audit. An assessment
may propose `same`, `related`, `different`, or `uncertain`; only exact `same`
with approval and a current revision may merge. A stale revision, changed entity,
missing approval, malformed assessment or failed audit leaves the graph intact.
The in-memory fixture is not a graph database transaction. A real host needs its
own atomic transaction proof and rollback ownership.

The [L seam test](../tests/test_use_case_graph_host.py) now builds a separate
synthetic host from the reviewed L recipe fixture, copies the matrix-pinned
`entities.py` unchanged, and pins a small [graph effect
adapter](../examples/use-case-host/graph_runtime.py) by byte hash. Its
baseline and alternative effects call `reconcile` with host approval, a separately retained
expected revision, the current graph revision and an audit
callback. A fresh inventory and source review bind the one-argument tail-call
seam; the existing implementation planner, baseline/modified verifier, apply
receipt and owned rollback execute on that host. A focused negative test
confirms stale expected revision or missing approval creates no merge record.
The [individual installed L journey](../tests/test_use_case_graph_installed.py)
extends that reviewed host with a normal console. Both the deterministic
baseline and generated alternative invoke the same code-owned consumer. The
#55/#56 path packages, installs, normally launches, observes raw in-memory
entities/revision/merge/audit records, disables, upgrades a separately reviewed
fixture version and rolls back its owned generation and source edits. The
consumer requires a finite action, current revision, approval and fresh output
path; the test reads the effect against independently constructed expected
bytes. This is not a persistent graph database transaction or independent
database readback. The combined console fixture's L record remains separate;
#54 L-specific bind, provider authority and benefit are pending. See the
[L operator reference](graph-template-offline-v1.md).

### D: retrieval evidence

Bind a query, stable passage/source/span/claim IDs, stance metadata, retriever,
and generation consumer. Missing evidence does not generate an answer. A
contradictory passage for a selected material claim remains in the evidence
bundle even when its initial relevance label is negative. Stance is metadata,
not a truth label; the separate generator and independent answer evaluation
remain necessary. Unsupported: missing provenance, ambiguous IDs, or a target
without the reviewed handoff seam.

The [individual D installed journey](../tests/test_use_case_retrieval_host.py)
copies the unchanged matrix-pinned RAG source into a separate reviewed host,
then binds a byte-pinned consumer and external finite corpus to a D tail-call.
The host checks exact corpus bytes/revision, approval and retained material
conflicts before a deterministic evidence formatter consumes the selected
bundle. The #55/#56 path installs and normally launches the off-mode console,
checks a raw cited effect against independently derived corpus expectations,
disables, upgrades a second reviewed fixture version, and rolls back its owned
generation and source edits. The formatter supplies an honest conflicting
evidence report, not a generative answer or truth determination. #54 D console
binding, provider operation and answer benefit remain pending. See the
[D operator reference](retrieval-template-offline-v1.md) for exact inputs and
limits.

### E: completion

Bind a finite objective, legal actions, independently read raw state and effect
receipts, and a bounded step owner. `result.success` cannot certify completion.
The fixture's `exact_goal` and `score_trace` check final state and each scheduled
checkpoint; partial, stale, or unrecorded effects fail. A real host must supply
its own raw observer and action/retry authority. No extra action or attempt is
authorized by an assessment.

The [individual E installed journey](../tests/test_use_case_completion_host.py)
builds a separate reviewed regular package around one E tail-call seam. It
copies the unchanged matrix-pinned completion oracle and the byte-pinned
[consumer adapter](../examples/use-case-host/completion_consumer.py), then
resolves a fresh inventory and source review. The host-approved
`close_and_label` consumer writes a raw final-state file and a separate
effect-receipt file. An independent expected-byte schedule and the pinned
oracle check actual completion; an executor's `ok` report alone is insufficient.
The #55/#56 path binds exact source, packages and installs offline, supervises
the normal off-mode console, observes both files, disables, upgrades a second
reviewed fixture version and rolls back to the retained first generation.
The #54 binder remains C-only, so E-specific `template bind` receipt linkage
is pending. See the [E operator reference](completion-template-offline-v1.md)
for inputs, commands, negative gates and limits.

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

The [individual H installed journey](../tests/test_use_case_retention_host.py)
uses a separate reviewed package host, not the six-case console. It copies the
exact matrix-pinned oracle and adapter bytes, re-scans the host, reviews a
single H tail-call seam, validates and materializes the template, and obtains
baseline, applied and modified receipts. The #55 package and install plans bind
the full applied host tree, exact wheelhouse and off-mode configuration. A #56
session launches the installed `retention-host` console and checks a fresh
external retained-state file against independently computed raw bytes, plus a
separate ready file. `/compact`, missing pin and changed selected source item
are rejected before any effect. A direct consumer case proves `/prune` can
drop the reviewed unpinned item; the installed off-mode fallback retains all
three items. Later recall is scored from the installed raw file. The first
session is disabled. A second reviewed package at version 1.0.1 is independently
installed, staged through exact upgrade authority, normally launched and
observed, then disabled; generation rollback restores version 1.0.0 while
retaining both installed environments. Both owned source edits are then
restored separately. This qualifies
only the Linux x86-64 CPython 3.13 synthetic off-mode H host. The current #54
console binder accepts recipe C only, so an H-specific `template bind` report
and its installed receipt linkage remain pending. Interruption and
connected/provider operation also remain pending. The
[H operator reference](retention-template-offline-v1.md) lists exact inputs and
limits.

## Whole-catalog support boundary

Python recipes A, B, C, D, E, F, G, H, I, J, K, L and M remain catalogued at
version 1.0 for the narrow `module-tail-call-v1` transform. For each of A, B,
F, G, I, J and K, use-case-specific source contract, installed execution,
connected mode and benefit are **not qualified by this checkpoint**. C points
to its separate #57 qualification; M remains source/oracle only.
L, D, E and H have the limited offline installed
journeys above. All connected cells remain pending. The separate JavaScript/TypeScript
`javascript.C@1.0` flat async backend has its own source catalog; it has no
L/D/E/M/H coverage and no installed Node journey from this checkpoint. All
rows remain mode **off**. Shadow, canary and active require separate authenticated
authority and their own evidence. Experiments #44–#49 retain independent
comparators and adoption decisions.
