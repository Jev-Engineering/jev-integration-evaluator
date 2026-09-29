# Native Windows template preparation checkpoint

This checkpoint inspects selected source bytes for a proposed Python console
host on local NTFS. It does not apply edits, create a private delivery bundle,
install a wheel, launch a process, isolate target code, or qualify provider
connectivity. The machine-readable receipt has `status: preparation_only` and
all apply/install/launch authority fields set to `false`.

## Proposed target and trust boundary

The read-only preflight accepts native x86-64 CPython 3.10, 3.13 or 3.14 on
Windows 11 (build 22000 or later) or Windows Server 2022 (build 20348), using
a local NTFS drive-letter root. These are preparation candidates, not versions
qualified for delivery. The local observed preparation run is Windows 11 Pro
build 26200, CPython 3.14.3. Windows Server delivery, other Windows/Python
combinations, ReFS/FAT, UNC and mapped/network paths are unqualified. WSL is a
separate Linux target.

The future delivery profile is a **trusted local host** profile. It will run
the reviewed installed console with the caller's Windows rights. It does not
provide a Windows sandbox for untrusted code; Linux seccomp cannot establish
that boundary. No live credential or provider may be inferred from this
preflight.

## Read-only command

Retain an independently reviewed private JSON manifest outside the host, for
example `C:\private\reviewed-source.json`:

```json
{
  "schema_version": "1.0",
  "files": {
    "pyproject.toml": "64 lowercase hex SHA-256 characters",
    "pkg/console.py": "64 lowercase hex SHA-256 characters"
  }
}
```

The digest strings above describe the format; replace them with actual reviewed
hashes. The command reads no target modules through Python imports and writes
no target or output file:

```powershell
python scripts/windows_template_preflight.py `
  --repo 'C:\src\reviewed-host' `
  --manifest 'C:\private\reviewed-source.json' `
  --output-parent 'C:\private\new-delivery-parent'
```

The output parent must already exist outside the host. The command prints only
status, platform, manifest digest, file count and explicit absence of delivery
authority; it does not print filenames, source or raw manifest content. The API
`inspect_windows_template_source(root, reviewed_file_hashes, output_parent)`
returns the full private report, validated by
`windows-template-preflight-v1.schema.json`. The caller must keep both the
reviewed manifest digest and any full report outside target source. A manifest
computed from a changed target is not an independent approval.

The check reuses discovery's handle-based drive/volume validation, reparse
ancestor and final-file checks, file identity, hard-link refusal, stable reads
and exact NTFS path checks. It rejects case-folded duplicate manifest paths,
unsafe components, source drift and an output parent overlapping the host.
Each selected file is limited to 2 MB; at most 32 selected files and 16 MB of
selected bytes are read. A second read catches edits observed during the
preflight. After each pass and before issuing the receipt, the check reopens
the lexical root path and compares its final path and NTFS file identity with
the original held root handle, rejecting an identical-content replacement.
This is a point-in-time check; a later mutation or installer must
recheck the exact files under its own ownership lock. Unselected files are not
reviewed by this receipt.

## Selected package-input inventory (read-only API)

`inspect_windows_template_package_inputs(host_root, reviewed_source_files,
wheelhouse, reviewed_wheels, output_parent, environment_parent, console_script)`
extends the point-in-time preparation check to an externally reviewed file map
of the traversed host source tree (up to 4,096 files/64 MB), selected wheelhouse files (up to 64
wheels/256 MB total), static `pyproject.toml` project, pinned setuptools/wheel
build requirements and console declaration, and the
current native interpreter executable hash. Each file and root is checked
twice; the source walk rejects unlisted files, reparse points, hard links,
ambiguous names, and directory identity drift. It skips directories named
`.git`, `.pytest_cache`, `__pycache__`, `build`, or `dist` at any depth and
records those exclusions in the report; bytes beneath them are not reviewed.
This inventory does not prove the set of inputs a future build hook may read.
Wheel bytes are hash checked
before reading bounded ZIP metadata and compatible wheel tags. Both output
and environment parents must already exist on disjoint local NTFS paths.

The API returns a private `windows-template-package-inputs-v1` report with
`status: package_inputs_reviewed_only`. Keep the reviewed maps and report in
an independently protected location. It does not authenticate the review,
verify an applied implementation receipt, create a private package or venv,
run build hooks or pip, qualify a launcher, or grant build/install/launch
authority. The report must not be passed to the Linux installer as its plan.
An eventual native installer must repeat exact checks under its own lock and
bind the externally retained applied-source and installation receipts.

## Native delivery adapter after the #56 contract merges

The next mutating stage needs a separate `plan/build` then `install-plan/install`
authority sequence. A Windows package plan must bind every actual build input,
including any files under the inventory's skipped directories that its build
can read, or prevent build access to them; it must then recheck that source map,
the #54 entrypoint binding and externally retained modified implementation
receipt, selected wheel hashes/tags, off-mode configuration, and exact native
interpreter. A source inventory receipt alone cannot authorize a build hook.
The build must copy checked bytes into an exclusively created owner-private
staging directory, disable index/user-site/Python path influence, record the
wheel hash after the hook, and reconcile an interrupted build before reuse.

The installer must create one owner-private NTFS generation with a protected
DACL, use `Scripts\\python.exe` and its native console launcher, install only
hash-locked offline wheels, then verify distributions, import origins, RECORD
hashes, launcher bytes and off-mode config. It needs a cross-process Windows
file lock, durable intent/journal writes and exact generation ownership.
Read-only status must distinguish a completed anchored install from a pending
or interrupted one. Locked files, ACL denial, read-only attributes, reparse
points, hard links and changed source/wheel bytes must block recovery instead
of prompting a blind recursive delete.

The supervisor can reuse #56's plan/session/scope/observation separation only
after adapting its Linux-only process path. A native launch needs a retained
Windows process handle and creation time, verified executable origin, one
durable launch-pending event before process release, and a job or equivalent
owned stop boundary. Repeated launch, cancellation, crash reconciliation,
observation drift and exact owned rollback need native tests. `TerminateProcess`
must never target a PID without confirming the retained process identity. This
trusted-local-host profile has no untrusted-code isolation claim. Connected
mode remains behind its own source/config/egress/receipt gates and live evidence.

## Delivery requirements still pending

The implementation lifecycle has a Windows `msvcrt` lock path, but POSIX mode
bits, `chmod` and path checks do not establish an owner-only Windows DACL,
durable replacement, or identity-stable rollback. The existing installer uses
`fcntl`, `O_NOFOLLOW`, POSIX uid/mode and `venv/bin/python` symlink assumptions;
its supported profile is Linux x86-64 CPython 3.13. The repository session
journal is POSIX. The #56 supervisor currently relies on Linux process identity
and stop semantics. Discovery success cannot expand any of those contracts.

A native adapter must independently test protected owner DACLs for journal,
bundle and configuration artifacts; NTFS volume/file IDs and no reparse or
hard links; file ACL and read-only-attribute preservation; case and long-path
behavior; cross-process locks; flush/replace/recovery after interruption; and
file-open conflicts. Installation must bind an independently retained modified
implementation receipt, source snapshot with explicit traversal exclusions, exact wheel hashes, native
`Scripts\\python.exe` and console launcher, and an owned environment generation.
The supervisor must bind a Windows process handle, creation time and executable
origin to one session, reject duplicate starts, observe exit/cancellation,
reap only its owned process, and preserve unrelated work. Upgrade and rollback
must verify exact owned bytes and attributes, restore the prior generation, and
fail closed on drift or a locked file. Connected modes still need independent
source/configuration, egress, receipt and holdout authority.

For a preflight failure, inspect its fixed `reason`, restore the reviewed source
or prepare a fresh independently reviewed manifest, and rerun. This checkpoint
changes no files and therefore has no rollback operation. Do not use its digest
as a substitute for an apply, install or supervisor receipt.
