# L graph identity offline host: operator reference

This is a synthetic Linux x86-64 CPython 3.13 qualification of the narrow
`python.L@1.0` tail-call host in mode `off`. The source contract pins the
unchanged [graph oracle](../examples/graph-system/entities.py) and the
[host graph consumer](../examples/use-case-host/graph_runtime.py) by exact
bytes. `inspect_use_case_source(root, "L")` reads both without importing
target modules. It cannot bind an arbitrary graph database.
This fixture tests identity reconciliation of two already supplied entities;
it neither extracts a graph from source material nor retrieves answers from it.

Run the focused offline journey with a previously prepared private wheelhouse:

```bash
JEV_TEMPLATE_WHEELHOUSE=/absolute/private/wheelhouse \
  python3.13 -m pytest -q tests/test_use_case_graph_host.py \
    tests/test_use_case_graph_installed.py
```

The test builder creates a separate reviewed regular `graph_host` package
with one L tail-call seam. It copies the graph oracle unchanged and the
byte-pinned consumer, then rescans the host. The old host's deterministic
baseline action and the generated alternative both use the same code-owned
graph consumer; the generated adapter is not hand-edited. It validates and
materializes the template, plans the exact source edit, runs isolated baseline
verification, applies, and checks the modified receipt. The #55 package and
install plans bind the applied tree, external modified receipt digest,
template, offline wheels, build tools and off-mode configuration. A #56
session with an externally retained install receipt and exact expiring scope
normally launches the installed `graph-host` console.

The consumer accepts only the finite `reconcile_same` request with a task ID.
Host-owned approval, current revision, separately retained expected revision,
two exact entity snapshots and pre-mutation audit are required. It calls the
unchanged `reconcile` oracle. The installed fixture supplies `GRAPH_DB_PATH`
for an external SQLite file under an owner-private `0700` directory. A
`BEGIN IMMEDIATE` transaction checks the stored entities, provenance and
revision, inserts the audit before the merge record, advances the revision
with a compare-and-swap, and commits both records together with SQLite full
synchronous mode. A separate read-only connection checks committed entities,
revision, and the full ordered audit/merge receipt history before an effect is
reported. A historical receipt changed without changing row count is refused.
Stale revision,
conflicting entity, missing approval, changed action or failed audit creates
no new merge or release file. Tests independently query the database and
compare it with the installed console's raw effect; the database itself is
the durable fixture effect, rather than a JSON assertion about in-memory
state. `GRAPH_EFFECT_PATH` and `GRAPH_READY_PATH` remain separate external
files; the JSON effect is exclusive, mode `0600`, and fsynced.

The test disables the first generation, builds and installs a separately
reviewed 1.0.1 fixture version, stages and launches it under a new exact
scope, reads its graph effect, disables it and rolls the session back to the
retained 1.0.0 generation. Both owned source edits are restored. The two
versions have identical finite graph semantics. Generation rollback does
not reverse either graph effect.

The #54 console binder remains C/E-only, so an L-specific bind receipt is
pending. This SQLite transaction records reconciliation of one fixed pair; it
does not collapse the two entity rows into a canonical node or reject a repeat
of the same pair under a later approved revision. It does not synthesize a
graph from documents, authorize semantic identity, or measure graph quality.
The classifier always proposes `same` for those two fixed entities. Database
file creation, merge-record commit and JSON effect creation are
not one transaction: an interrupted post-commit JSON write requires manual
reconciliation, never blind retry. The test does not establish concurrency
across independent hosts, arbitrary entity identity, connected/provider
authority, or production approval. Generation rollback retains both database
effects; it does not reverse a reconciliation record.
