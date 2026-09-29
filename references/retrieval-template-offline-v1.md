# D retrieval offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification for the narrow
`python.D@1.0` tail-call profile in mode `off`. The source contract pins the
unchanged [RAG oracle](../examples/rag-system/pipeline.py), the separate
[retrieval consumer](../examples/use-case-host/retrieval_consumer.py), and the
finite [corpus](../examples/use-case-host/retrieval_corpus_v1.json) by exact
bytes. `inspect_use_case_source(root, "D")` reads those bytes without importing
the target. This does not bind an arbitrary RAG application.

Run the focused offline journey with a previously prepared private wheelhouse:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_retrieval_host.py
```

The test builds a separate regular `retrieval_host` package with a reviewed
one-argument D tail-call seam. It validates and materializes the template,
plans the exact source edit, records baseline verification, applies the edit,
and verifies the modified host. The generated adapter is not hand-edited.
The #55 package/install plan binds the applied source tree, external modified
receipt digest, materialized template, pinned wheelhouse/build tools, and
off-mode configuration. The installed receipt identifies the owned console.
An externally retained install receipt digest and a distinct expiring scope
feed the #56 session for normal installed `retrieval-host` launch.

The host reads an already existing private `D_CORPUS_PATH` file, checks its
exact reviewed hash and revision 7, and requires host approval plus the
expected revision. The corpus carries stable passage, source, span, claim,
stance and provenance fields. The generated D selection must include the
supporting hit and the initially irrelevant contradictory and uncertain
passages for the same material claim. Missing, changed, stale, ambiguous or
unauthorized inputs refuse the write. The consumer calls the unchanged
`answer_with_evidence` oracle with its lexical baseline and a real code-owned
deterministic formatter. The formatter emits a cited evidence bundle that
explicitly describes conflict; it does not assert which source is true.
No LLM or provider is called in this qualification.

`D_EFFECT_PATH` and `D_READY_PATH` are fresh absolute files under a private
`0700` directory outside source, package, environment and session roots. The
consumer writes the raw effect with exclusive owner-only creation and fsync.
The test independently derives expected bytes from the pinned external corpus,
reads the installed command's effect file and checks the cited source IDs,
quotes, stances, selected IDs and lexical decisions. A verifier probe uses a
per-process output path; this is still a synthetic host effect, not an
independent retrieval service or measured answer quality.

The lifecycle test disables the first generation, builds and installs a
separately reviewed 1.0.1 fixture package, stages and normally launches it,
reads the second effect, disables it, and rolls the session back to retained
1.0.0. It then restores both owned source edits. The two versions have the
same finite retrieval semantics; generation rollback does not erase either
effect. Wrong package/install approvals, changed consumer bytes, bad launch
scope, source/corpus drift, stale revision, missing corpus or effect path,
missing contradiction, and denied host approval fail closed in focused tests.

The #54 console binder currently supports recipe C only; a D-specific bind
receipt remains pending. This fixture does not qualify untrusted target
retrievers, arbitrary queries, a generative answer model, connected authority,
provider operation, answer correctness, task benefit, interrupted upgrade or
cross-process task deduplication. A real host needs its own retriever and
generation authority, source provenance, raw answer evaluation and retry
ownership before those cells can be promoted.
