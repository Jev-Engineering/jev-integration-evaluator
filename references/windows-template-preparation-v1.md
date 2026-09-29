# Native Windows template preparation checkpoint

This checkpoint inspects selected source bytes for a proposed Python console
host on local NTFS. It does not apply edits, create a private delivery bundle,
install a wheel, launch a process, isolate target code, or qualify provider
connectivity. The machine-readable receipt has `status: preparation_only` and
all apply/install/launch authority fields set to `false`.

An independently scoped [native offline API checkpoint](windows-template-native-delivery-v1.md)
now covers one locally observed installed off-mode console journey; this
preparation receipt remains read-only and grants none of that authority.

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
The separate native installer repeats exact checks under its own lock and
binds the externally retained applied-source and installation receipts.

## Native delivery design boundary

The separate [native offline API checkpoint](windows-template-native-delivery-v1.md)
uses a two-stage exact package plan/build followed by install plan/install.
It verifies the externally retained applied-source receipt and copied source,
uses only checked files in a protected staging root, installs hash-locked
wheels into a protected NTFS venv, and runs one gated normal console under a
Windows Job Object. This read-only preparation report cannot stand in for any
of those effect authorities. The mutating checkpoint remains a trusted-local-
host execution profile and has not completed issue #61 qualification.

## Delivery requirements still pending

The original #55 installer and #56 supervisor retain their Linux-only
profiles. The repository session journal is POSIX. The native checkpoint
uses separate NTFS owner artifacts and Job Object process ownership; it has
not replaced the Linux contracts or completed a Windows upgrade/rollback path.

Full #61 qualification still requires the supported Windows/Python matrix,
native ACL denial, real reparse ancestors, hard links, case collisions, long
paths, read-only and locked files, concurrent source edits and interruption
tests against the mutating path. It also requires independent ready/effect
observations, cancellation and upgrade/rollback with exact owned bytes and
attributes. Connected modes still need independent source/configuration,
egress, receipt and holdout authority.

For a preflight failure, inspect its fixed `reason`, restore the reviewed source
or prepare a fresh independently reviewed manifest, and rerun. This checkpoint
changes no files and therefore has no rollback operation. Do not use its digest
as a substitute for an apply, install or supervisor receipt.
