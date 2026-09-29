# Native Windows offline template delivery checkpoint

This API checkpoint builds and installs an already applied, independently
verified Python console host, then launches its normal installed console in
`off` mode under a Windows Job Object. A bounded run ledger can select a newer
disjoint installed generation and return to a retained old generation through
a fresh child session. It is a trusted local host execution profile. It does
not isolate untrusted Python, authorize a provider, or establish benefit.

The observed local path is Windows 11 Pro build 26200, x86-64 native CPython
3.10.11, 3.13.13 and 3.14.3 on local NTFS. Each interpreter has a retained
private three-generation receipt archive. The profile parser also accepts
Windows Server 2022, whose mutating and installed journeys have not run.
The retained 3.10 and 3.13 runs verify the bounded install receipt. A later
retained 3.14 run verifies the current fail-closed process and Job queries;
an earlier 3.14 archive remains historical evidence from before those fixes.
WSL is a separate Linux target. UNC/mapped drives, non-NTFS volumes, Windows
10, and virtualized or container delivery are unsupported.

## Source and package authority

Use `prepare_template_binding`, `materialize_template`, the #54 exact
implementation plan/apply/baseline/modified verification flow, and retain the
modified receipt digest outside the target. The package request requires:

- `host_root`, a complete independently reviewed `reviewed_source_files` hash
  map for the declared traversal, `implementation_bundle`,
  `trusted_modified_receipt_sha256`, and `template_directory`;
- an owner-private offline `wheelhouse`, independently reviewed
  `reviewed_wheels` hashes, disjoint existing `output_parent` and
  `environment_parent`, the exact `console_script`, and the current native
  `interpreter`;
- `configuration` with `jev_runtime.mode: off` and its independently retained
  `reviewed_configuration_sha256`.

Call `plan_windows_template_package(request)`, review its exact
`plan_sha256`, then `build_windows_template_package(plan,
approved_plan_sha256=...)`. Retain the package receipt digest externally.
Call `plan_windows_template_install(package_plan, package_receipt,
trusted_package_receipt_sha256=...)`, review its digest, then
`install_windows_template_package(plan, approved_plan_sha256=...)` and retain
the install receipt digest. `windows_package_status` and
`windows_install_status` are read-only and distinguish absent, interrupted,
recorded-untrusted and externally anchored results.
Before returning `absent` or creating a generation, both stages inspect the
plan-derived root without following its final component. An existing dangling
NTFS junction blocks ownership and effect replay. A native disposable junction
test covers package and install status and build/install entrypoints while
checking that the unrelated target directory remains intact.
The install planner rereads the package receipt from the plan-derived
owner-private generation and requires the caller's entire receipt to equal
that record. Session creation similarly rereads the private install receipt,
requires exact equality, and binds the native Python and console paths to
the owned venv. The launch rechecks that binding before any process release;
an authentic digest attached to substituted caller fields grants no authority.

The build stage copies **only** the reviewed selected files into an exclusively
created owner-private source directory. Excluded `.git`, `.pytest_cache`,
`__pycache__`, `build` and `dist` trees never enter that stage. The plan
accepts pinned `setuptools.build_meta` and static metadata only; root
`setup.py`, `setup.cfg`, custom command classes and dynamic metadata are
unsupported. This is a trusted-host boundary: build tooling itself is pinned
and hash checked, but it is not a sandbox for malicious build hooks. No index,
target compiler configuration, global package installation or user site is
used. A failed build or install retains an immutable intent and its owner
directory for review; it cannot be blindly replayed or deleted.

The installer makes a separate protected NTFS venv generation, installs only
hash-locked offline wheels, checks dependency closure, wheel RECORD, native
console metadata/import origin, executable hashes and the exact off config.
Its receipt inventories every file hash, file/directory ACL and NTFS identity
in the private venv so an added import hook such as `sitecustomize.py`, an ACL
change or identical-byte replacement invalidates later status and launch. The
venv's entire tree is rechecked immediately before release of the console gate.
An exclusive sharing handle held on the installed `config.json` makes the
existing native Windows install status unavailable and blocks a new child session;
replaying the same generation is refused. Closing the handle restores exact
receipt validation without deleting or rewriting the generation. A disposable
installed-host test now covers this existing behavior with a real Win32 sharing
lock and checks that no session directory is created and unrelated bytes remain
intact. The unchanged `94d355b` implementation passes that same test. This
qualifies one locked-file refusal, not the broader locked-root, ACL and
interrupted-install matrix.
The complete Python 3.10 venv inventory produced a 1,276,216-byte install
receipt. This one named owner record has a finite 4 MB read/write limit;
other owner records retain the 1 MB limit. Larger installs fail closed.

## One supervised invocation

Call `create_windows_template_session(new_directory, install_plan,
install_receipt, trusted_install_receipt_sha256=...,
launch_environment={...})`, then review its `session_sha256` and call
`launch_windows_template_session(session, install_plan,
approved_session_sha256=...)`. The optional environment has at most 16
nonsecret uppercase variables; Python, pip, runtime mode and secret-like
variable names are rejected. The supervisor supplies `JEV_RUNTIME_MODE=off`
and disables user site and bytecode writes.

The supervisor writes an immutable launch intent, starts a helper blocked on
an inherited pipe, creates a unique named Job Object, assigns the helper,
records PID, creation time, executable image and job name, rechecks the exact
install, then releases one byte to run the normal console launcher. A trusted
guardian retains the named Job handle until the exact gated process exits. The
Job has kill-on-last-handle-close set, so guardian failure ends its owned
members rather than leaving a live console outside the recorded Job. A
session binds the trusted base CPython interpreter path and file hash used by
the guardian; launch rechecks both before spawning it. Earlier session records
without this binding remain readable for status and owned stop, but cannot
authorize a fresh launch. A repeated attempt is refused.
`windows_session_status` reads the private
records and checks the exact live process and job membership without importing
target code. An exited console is `exited_unverified` until an independent host
observation verifies its effects. Status does not treat host success JSON as
proof of integration or provider reachability. Unknown process access, a
missing or inaccessible Job while the exact process is live, and uncertain
membership block status, effect observation and owned stop. Only a confirmed
signaled process handle or a known absent PID counts as exit.

`observe_windows_template_session(session,
approved_identity_sha256=..., phase='ready'|'effect', path=...,
expected_sha256=...)` reads an external, predeclared marker with the exact
recorded process and Job identity. A ready marker is accepted only while the
Job member is running; an effect marker only after exit or owned stop. The
caller supplies the expected bytes digest independently. A matched marker is
host evidence, not a provider result or launch authority. The fixture writes
an entry-ready marker during startup options, then a task-effect/cleanup JSON
at process exit; the observer checks these as separate phases. The ready report
also snapshots at most 64 live members of the exact named Job with PID,
creation time and executable image. A changing or oversized member list blocks
the observation; the snapshot is a point-in-time fact, not a persistent process
handle.

`stop_windows_template_session(session,
approved_identity_sha256=...)` records stop intent and terminates only the
verified member's exact named job. It never signals a bare PID. It can stop a
live process even if a crash occurred after identity recording but before the
release record; that case remains `blocked_recovery` because effects may have
run. A launch intent without identity also blocks replay. Preserve the
directory and externally retained digests for reconciliation. A later process
with a reused PID, changed image/creation time, or changed job membership is
never stopped by this API.

## Retained installed-version run

`create_windows_template_run(new_directory, install_plan, install_receipt,
trusted_install_receipt_sha256=..., launch_environment=...)` records one
owner-private run and its initial child session without launching it. Retain
the returned `selection_sha256` outside the run directory. Launch the returned
`selected_session` with its matching install plan and exact session digest;
then observe and stop it through the session APIs above.

After the old child has stopped, `upgrade_windows_template_run(directory,
old_plan, new_plan, new_receipt, approved_selection_sha256=...,
trusted_new_receipt_sha256=...)` requires the same project, a strictly newer
PEP 440 version, a disjoint owned install, and current old/new receipt and
source checks. It writes an immutable stage intent before creating the new
child. After the new child stops, `rollback_windows_template_run(directory,
retained_plan, retained_receipt, approved_selection_sha256=...,
trusted_retained_receipt_sha256=...)` rechecks the retained old install and
creates a fresh child there. Both operations keep the same `run_id`, preserve
the old and new package/install/session directories, and never launch
automatically. The maximum is three selected sessions: initial, upgrade and
rollback. Further upgrade requires a newly reviewed run.

`windows_template_run_status(directory,
trusted_selection_sha256=...)` is read-only. Without an externally retained
selection digest, it marks the recorded selection untrusted and does not return
the selected session object. If a stage stops after its durable intent,
`resume_windows_template_run(directory, plan, receipt,
approved_intent_sha256=..., trusted_install_receipt_sha256=...)` can finish
only that same stage and run. A complete, unlaunched child can be adopted after
exact receipt and executable checks. A partial or possibly launched child
blocks for review; it is never deleted or replayed. This rollback selects a
retained installed version; it does not undo #54 source edits. Restore source
only through the independently reviewed #54 exact rollback with current
ownership/ACL checks.

An interrupted install or launch still requires read-only status and manual
review before a fresh generation is authorized. This checkpoint does not
provide provider-connected activation or a Windows isolation backend.

## Local offline installed check

In a disposable workspace with an owner-private wheelhouse containing the
exact reviewed native wheels, the installed fixture driver is:

```powershell
$env:JEV_WINDOWS_TEMPLATE_WHEELHOUSE = 'C:\private\reviewed-wheels'
& '.venv\Scripts\python.exe' -m pytest -q tests/test_windows_template_delivery.py
```

It executes fixture source binding, applied-source verification, offline
wheel build/install, gated normal console invocation, duplicate-launch and
owned-stop checks, plus installed-tree drift and dangling-generation-junction
refusal. It also checks exclusive-share lock refusal on the installed config
and exact status recovery after that handle closes. The separate
`tests/test_windows_template_run.py` exercises two installed versions,
retained rollback, same-run interrupted-stage recovery, and separate ready
and effect observations. It is a synthetic
host observation, not live provider or production evidence. The wheelhouse
is explicit and must contain matching platform tags, all runtime dependencies,
and exact pinned build wheels. The local runs used isolated CPython 3.10.11,
3.13.13 and 3.14.3 venvs and owner-private, platform-specific wheelhouses;
no global install or credentials. A fixed private pytest root retained the
passing 3.10 run receipts, alongside separate 3.13 and 3.14 archives. Windows
Server mutating/installed runs, broader crash and
filesystem edge cases, and provider qualification remain pending before
marking issue #61 fully qualified.
