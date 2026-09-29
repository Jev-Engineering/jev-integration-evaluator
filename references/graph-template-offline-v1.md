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
unchanged `reconcile` oracle; stale revision, missing approval, changed
action or missing output path refuses the effect. `GRAPH_EFFECT_PATH` and
`GRAPH_READY_PATH` are fresh external files. On Linux their parent is
owner-private `0700`; graph output is created exclusively, mode `0600`, and
fsynced. The output contains the in-memory store's entities, revision,
merge receipt and audit record after mutation. The test independently
constructs expected raw bytes, reads the installed command's output and
checks revision/provenance/receipt/audit equality. This is a raw effect from
the same synthetic host process, not an independent database observer.

The test disables the first generation, builds and installs a separately
reviewed 1.0.1 fixture version, stages and launches it under a new exact
scope, reads its graph effect, disables it and rolls the session back to the
retained 1.0.0 generation. Both owned source edits are restored. The two
versions have identical finite graph semantics. Generation rollback does
not reverse either graph effect.

The #54 console binder remains C-only, so an L-specific bind receipt is
pending. This profile does not prove persistent database transaction or
rollback semantics, concurrency across processes, dynamic entity identity,
connected/provider authority, or measured graph quality. The synthetic
classifier always proposes `same`; it does not establish semantic entity
identity. A real host needs its own transactional graph store, authenticated
approval and audit, revision ownership, and independent graph readback.
