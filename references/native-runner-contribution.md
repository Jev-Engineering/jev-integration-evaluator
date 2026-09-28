# Native runner and repository session draft — issue #8 qualification pending

Contribution contract: `linux-chroot-seccomp-python-ro-v1` / schema `1.0`.
The opt-in `1.1` contract adds a selected installed environment with an
executable that resolves to the exact trusted worker interpreter inode and an
explicit pure-Python dependency snapshot. This limited mode does not launch
target-provided interpreter code before isolation. It copies approved `.py`
modules and distribution `METADATA` into `/deps`, verifies bytes and modes at
each case and after execution, and adds `/deps` to `sys.path` only after
chroot, credential drop, and seccomp installation. The selected path, binary
hash, dependency root identity, package metadata, and file hashes are bound to
the `1.1` request and receipt. Missing, changed, or incompatible interpreters
and dependencies fail without falling back. Binary extensions, `.pth` files,
other interpreter builds, and unlisted packages are unsupported.
The `1.1` source snapshot also rejects copied shared-library artifacts;
qualified code paths are Python source and approved passive assets only.
The `1.1` specification also carries exact code-owned isolation capabilities:
Linux x86-64, read-only copied files, denied network/process/thread/exec
syscalls, same-inode interpreter, and declared pure-Python dependencies.
Changing any capability field fails contract validation.
The dedicated ephemeral CI job compares the full kernel, architecture,
interpreter, libseccomp, worker, supervisor, and runtime-closure identity to
`validation/native-runner-environment-lock.json` before executing required
privileged cases. A changed hosted image or source byte requires review and a
new lock; a green generic test matrix cannot substitute for this job.
The runner remains opt-in. The repository command now has a separate isolated
session path using `repository-run-scope-v1` schema `1.1` and a
`repository-native-contract-v1` contract. Legacy `1.0` scopes, verifier receipts,
and trusted-host execution remain available. No native receipt is copied into a
legacy verifier field. This draft does not connect TypeSafe runtime bootstrap or
authorize activation.

## Execution model and scope

The caller supplies an absolute repository path, an exact explicitly enumerated
file/asset manifest, a bounded schedule of Python script entries and arguments,
an environment identity, resource limits, and an **externally supplied** grant
bound to the complete request digest. `prepare_spec` reads only the specified
files and executes only the code-owned launcher in describe mode; it never
imports, compiles, or executes the target during preparation. It does not invent
an execution approval. The embedding application must authenticate the caller
and its authority reference. A digest is a binding, not an authentication system.

Execution is a fresh interpreter process launched with `-I -S`, no inherited
application environment, no shell, no target interpreter/plugin configuration,
and no dependency installation. A code-owned worker enters a private jail,
changes cwd into it, closes external descriptors, drops all real/effective/saved
UIDs and GIDs to 65534, clears supplementary groups and effective/permitted/
inheritable capabilities, disables dumpability, and sets no-new-privileges.
The worker sets its parent-death signal after dropping credentials and checks
that its parent did not change. Only the disposable child changes these settings.

A native-ABI libseccomp allowlist is installed before any target source is
compiled. Non-native ABIs are killed; every unlisted syscall is denied. The
filesystem is a root-owned, non-writable copied tree with no `/proc`, devices,
sockets, writable directories, or host directory descriptors. Approved file
bytes and modes are retained exactly; modes outside 0444/0644/0555/0755 are
unsupported rather than silently changed. Network sockets, process/thread
creation, execution of new programs, privilege changes, namespace/mount changes,
peer-process access, `ptrace`, `io_uring`, and filesystem mutations are not allowed.

The supervisor enforces a wall-clock deadline, total schedule deadline, combined
stdout/stderr retention limit and process-group kill/reaping. The child enforces
address-space, CPU, descriptor, core-file, process and file-size limits. The v1
policy does not allow descendant creation; attempted fork/clone is rejected.
There is **no qualification of workloads that intentionally spawn descendants**.
A separate disposable test supervisor verifies worker termination and reaping
when its parent dies. No shared host subreaper or infrastructure is changed.

The source snapshot, approved argv, exact interpreter binary, kernel/machine,
worker and supervisor code, libseccomp bytes, and preloaded module/shared-library
closure are bound to the request. Original source and copied phase bytes/modes
are checked again. Missing or changed prerequisites do not select a different
interpreter, install a dependency, or fall back to unsandboxed execution.

## Supported execution in this checkpoint

Only the pinned ephemeral Linux x86-64, privileged-launcher, CPython 3.13.5
environment is qualified for the standalone runner. The repository session
integration still requires its own passing hosted and independent review gates.
Targets are explicitly scoped synthetic Python scripts with
builtins, trusted preloaded modules, and explicitly supplied source dependencies.
The script's actual `__main__` runs; the worker does not replace its runtime
factory. A hand-authored fixture tests real startup, baseline-equivalent off/
shadow behavior and closure. That fixture is **not** the TypeSafe HTTP client,
SafeRouter, HostGate or BudgetCoordinator and does not qualify issue #12.

## Unsupported and unqualified

Windows, macOS, non-x86-64 Linux, nonprivileged/rootless launch, other Python/kernel
versions, writable target filesystems, spawned processes or threads, sockets,
provider connectivity, nonidentical target interpreter builds, compiled
dependencies, arbitrary framework or
stdlib dependency discovery, ESM/CommonJS/TypeScript execution, generated JEV
recipe shadow activation, arbitrary installed-host compatibility, composite transactions and production
activation are not qualified by this contribution. There is no automatic host
fallback. The standalone wheel test qualifies only this contribution's packaging,
not the complete evaluator wheel or an installed real-world host application.

No protection against kernel vulnerabilities, a malicious privileged host,
physical attacks, microarchitectural side channels, or disclosure deliberately
sent to an explicitly authorized output reader is claimed. This code needs an
independent security review and full integration qualification before exposure
to arbitrary or private hosts. The local tests execute only disposable synthetic
fixtures expressly covered by the development task.

## Receipt semantics

All valid scheduled cases retain a row: failures, timeouts, blocked prerequisites,
and unrun deadline cases remain in the denominator. Cases are never retried or
replayed automatically. `target_launch_released` reports that the trusted worker
established isolation and released the target launch boundary; it is **not** an
independent observation that the host entrypoint completed.

A private setup pipe closes before target compilation. Target stdout, including
JSON that claims `verified: true`, cannot create an enforcement receipt. Public
runner receipts contain hashes, counts, bounded timings, exit codes and failure
classes, not raw target output or source. Raw bounded output remains in the
private API result for a separately authorized independent observer.

`inspect_receipt` checks exact schedules, counts, command/source/environment
bindings and exit-code consistency. An externally retained expected digest can
anchor a record; a self-consistent digest cannot authenticate itself. In every
case, `integration_verified` and `activation_eligible` remain false. Exit zero,
synthetic wiring, connectivity, measured benefit and activation are distinct.
`runners.observations.inspect_lifecycle_postconditions` consumes a separately
frozen, externally anchored `native-postconditions-v1` oracle and externally
anchored baseline/modified receipts. Its `json-state-v1` adapter checks actual
entry reachability, result, effects, state, assessment count and dependency
origin against exact source-bound expected values, then checks baseline/off/
shadow parity. Every scheduled failure or unrun case remains a report row.
The returned postcondition report still declares `integration_verified=false`:
session dispatch checks repository/context/bundle, source phase, attempt and
anchors before reporting a verified synthetic session. Oracle authorship and
scope principal authentication remain external trust responsibilities.
The runner-owned `private_archive` helper writes bounded raw outputs once to a
private 0700 directory as an exclusive 0600 file, fsyncs file and directory,
and returns its digest for external retention with the phase and attempt. A
readback requires the exact external receipt and archive digests, checks every
scheduled case against receipt output hashes, and rejects missing, changed or
wrong-phase archives. It never retries a target to regenerate lost output.

The standalone CLI creates an exclusive private receipt path and fsyncs a
`started_uncompleted` marker before execution. It refuses to reuse or overwrite
that path. Interruption cannot turn it into a passed receipt. The separate
repository session uses the merged issue #4 journal and exact-head scope. Each
native phase writes its receipt and private output archive before journal
completion. A pending phase can be adopted only with separately retained exact
receipt and archive digests plus the same contract/oracle anchor; missing or
altered output blocks recovery without replay.

## API and command

```python
from jev_integration_evaluator.runners.isolated_python import (
    ExecutionGrant, prepare_spec, request_digest, run_schedule,
)

# Read-only preparation. Substitute an explicitly authorized synthetic path.
spec = prepare_spec(
    absolute_synthetic_root,
    ["entry.py", "runtime.py"],
    [{"case_id": "off", "entry": "entry.py", "argv": ["off"]}],
)
# For the supported same-interpreter installed pure-Python subset, add:
# target_environment={
#   'interpreter_path': '/approved/venv/bin/python',
#   'dependency_root': '/approved/venv/lib/pythonX.Y/site-packages',
#   'files': ['package/__init__.py', 'package-1.0.dist-info/METADATA'],
#   'distributions': [{'name': 'package', 'version': '1.0',
#                     'metadata_path': 'package-1.0.dist-info/METADATA'}],
# }
# Display/store spec for review. Do not automatically create a grant from it.
# Only after the trusted caller supplies the exact approval and scope reference:
grant = ExecutionGrant(externally_approved_digest, externally_supplied_reference)
result = run_schedule(absolute_synthetic_root, spec, grant)
```

```sh
python scripts/run_native_runner.py \
  --repo /absolute/authorized/synthetic-host \
  --spec /absolute/private/reviewed-runner-spec.json \
  --approve-execution-digest EXACT_EXTERNALLY_APPROVED_REQUEST_SHA256 \
  --authority-reference EXISTING_AUTHORITY_REFERENCE \
  --receipt /absolute/private/NEW-receipt.json
```

Exit 0 means every scheduled command exited zero and original source identity
still matched, **not** that the application integration was verified. Exit 2 is
invalid input/authority/I/O; exit 3 preserves unsuccessful scheduled execution.
Do not run this against arbitrary third-party or production targets. Do not
install credentials or elevate privileges just to make a missing backend pass.

## Required qualification before issue closure

The repository session now dispatches isolated baseline and modified schedules
from a reviewed native contract, uses a distinct native baseline gate for apply,
and retains private output archives with bounded attempts. The hosted synthetic
session fixture calls an actual edited host entrypoint, reads a selected pure
Python dependency from `/deps`, and checks baseline/off/shadow effects and state.
Its shadow assessment is a deliberately separate synthetic probe; it does not
prove generated JEV router activation or TypeSafe provider wiring.

Complete the passing hosted session and crash/recovery gate, full evaluator
regressions, demos, release/checksum validation, installed artifact checks and
independent security review. Validate any proposed real host's interpreter and
dependency closure separately before use. Do not treat a schema-valid oracle or
local journal as a substitute for an authenticated external reviewer or anchor.

## Primary technical references

The mechanisms are composed; chroot and seccomp individually are not complete
sandboxes. Consult the actual platform's documentation during independent review:

- Linux kernel seccomp filter documentation: https://docs.kernel.org/userspace-api/seccomp_filter.html
- Linux `chroot(2)`: https://man7.org/linux/man-pages/man2/chroot.2.html
- Linux no-new-privileges: https://man7.org/linux/man-pages/man2/PR_SET_NO_NEW_PRIVS.2const.html
- libseccomp architecture handling: https://man7.org/linux/man-pages/man3/seccomp_arch_add.3.html
- libseccomp filter attributes: https://man7.org/linux/man-pages/man3/seccomp_attr_set.3.html
