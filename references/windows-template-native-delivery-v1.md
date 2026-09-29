# Native Windows offline template delivery checkpoint

This API checkpoint builds and installs an already applied, independently
verified Python console host, then launches its normal installed console in
`off` mode under a Windows Job Object. It is a trusted local host execution
profile. It does not isolate untrusted Python, authorize a provider, establish
benefit, or qualify the complete #61 upgrade and rollback lifecycle.

The observed local path is Windows 11 Pro build 26200, x86-64 native CPython
3.14.3 on local NTFS. The profile parser also accepts Windows Server 2022 and
CPython 3.10/3.13, but their mutating and installed journeys have not run.
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
install, then releases one byte to run the normal console launcher. A repeated
attempt is refused. `windows_session_status` reads the private records and
checks the exact live process and job membership without importing target
code. An exited console is `exited_unverified` until an independent host
observation verifies its effects. Status does not treat host success JSON as
proof of integration or provider reachability.

`stop_windows_template_session(session,
approved_identity_sha256=...)` records stop intent and terminates only the
verified member's exact named job. It never signals a bare PID. It can stop a
live process even if a crash occurred after identity recording but before the
release record; that case remains `blocked_recovery` because effects may have
run. A launch intent without identity also blocks replay. Preserve the
directory and externally retained digests for reconciliation. A later process
with a reused PID, changed image/creation time, or changed job membership is
never stopped by this API.

This checkpoint does not provide session upgrade, automatic source rollback,
provider-connected activation or a Windows isolation backend. Restore source
only through the independently reviewed #54 exact rollback and its current
ownership/ACL checks; do not delete retained package, install or session
generations as a substitute. An interrupted install or launch requires
read-only status and manual review before a fresh generation is authorized.

## Local offline installed check

In a disposable workspace with an owner-private wheelhouse containing the
exact reviewed native wheels, the installed fixture driver is:

```powershell
$env:JEV_WINDOWS_TEMPLATE_WHEELHOUSE = 'C:\private\reviewed-wheels'
& '.venv\Scripts\python.exe' -m pytest -q tests/test_windows_template_delivery.py
```

It executes fixture source binding, applied-source verification, offline
wheel build/install, gated normal console invocation, duplicate-launch and
owned-stop checks, plus installed-tree drift detection. It is a synthetic
host observation, not live provider or production evidence. The wheelhouse
is explicit and must contain matching platform tags, all runtime dependencies,
and exact pinned build wheels. The current local run used an isolated CPython
3.14.3 venv and an owner-private wheelhouse; no global install or credentials.
The required native matrix, upgrade/rollback, interruption and edge-case tests
remain pending before marking issue #61 fully qualified.
