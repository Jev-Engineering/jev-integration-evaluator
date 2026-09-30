# Installed Python source binding for connected review

`template connected-installed-bind` recomputes a read-only mapping between one
already verified source application, its built wheel, and the installed Linux
CPython 3.13 console generation. The command requires externally retained exact
package and install receipt hashes. It verifies the existing off-mode package
and install generations, the wheel `RECORD`, installed module bytes, and the
retained reviewed `pyproject.toml`. It does not import the target or launch it.
The Alpha 1.0.2 preparation checks the independently pinned host, console,
options loader, and project hashes before it generates an adapter; a changed
loader is rejected at source review.

The report records the distinct source path in the implementation specification
(`src/.../host.py`), installed wheel members (`package/host.py`, generated
adapter, and console), the selected installed origins and hashes, and the
retained project file. `binding_sha256` is an identity for the report, not an
approval. A connected host must independently authenticate that exact digest
and recheck the current files before startup and each routed operation.

The package and install plans remain off-mode provenance. This binding alone
does not grant provider egress, a credential, a connected launch, canary or
active exposure, or measured benefit. The separate [connected shadow delivery
profile](connected-delivery-v1.md) requires an independently authored host
options loader, exact expiring host-authenticated authority, an installed
runtime ledger, and its own durable supervisor.
