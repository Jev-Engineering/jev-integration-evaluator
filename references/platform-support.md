# Platform support matrix

This matrix separates the read-only `repository-discovery` contract from
repository sessions, implementation planning and runtime operations. A discovery
report is a bounded source snapshot; it is not an execution sandbox or a global
absence proof.

| Platform and filesystem | Repository discovery | Qualification |
| --- | --- | --- |
| Linux, including WSL2 Linux filesystems | Supported through POSIX descriptor-relative reads with `O_NOFOLLOW`. | Existing Linux CI and recorded Linux/WSL runs. This change does not restart or reconfigure WSL. |
| macOS with the required POSIX descriptor operations | Existing backend retained. | No macOS runner was added by issue #42; current macOS versions are not newly qualified here. |
| Windows 11, CPython 3.14.3, local NTFS drive | Local discovery and source-bound preparation fixtures pass; this account cannot create real symbolic links. | The local suite covers handle identity, ACL denial, junctions, long paths and explicit link classification. CI must still qualify real symbolic-link behavior. |
| Windows Server 2022 hosted runner, NTFS, CPython 3.10 and 3.13 | Qualification target for the same discovery and source-bound preparation commands. | The `windows-discovery` job provisions long-path and symbolic-link fixtures and fails on skips; support is claimed after both interpreter jobs pass. |
| Windows 10, ReFS, FAT/exFAT, network shares, mapped drives, and device paths | Not qualified. UNC and mapped network roots are rejected; non-NTFS and device paths return explicit blocked outcomes. | No discovery report is emitted for an unsupported root. |

## Native Windows paths

Run the installed public command from PowerShell with a local drive-letter root
and a new output file in an existing directory outside the repository:

```powershell
python -m jev_integration_evaluator repository-discovery `
  'C:\src\my-project' --out 'C:\jev-reports\capabilities.json'
```

CPython 3.10 or later is required by the package. Use an NTFS volume. The scanner
accepts ordinary drive paths and `\\?\C:\...` extended drive paths; it adds the
extended prefix internally for long-path operations. Drive-relative paths such
as `C:project` are rejected as ambiguous. A UNC path such as
`\\server\share\project`, its extended UNC form, or a mapped network drive is
rejected with `unsupported_unc_path`. Other device namespace paths are rejected
with `unsupported_device_path`.

No administrator rights or target-repository hooks are needed for a scan. The
caller needs the ordinary Windows list/read rights required for the source files
being considered. A denied source file or directory is recorded as an
`access_denied` limitation and the report has `discovery_outcome:
incomplete_analysis` and `coverage.complete_within_policy: false`. The CLI's
`status: written` means that this explicitly incomplete report was saved; it
does not mean the scan was complete. Inspect the report outcome before using it.
Interrupting with Ctrl+C returns a redacted `discovery_interrupted` result with
exit code 130 and creates no report.

Outputs are created exclusively and receive a protected owner-only DACL. Existing
files are not overwritten. Output paths inside the repository are rejected with
case-insensitive Windows path comparison. Reparse points in the output directory
path are rejected. External JSON inputs use the same component checks and reject
reparse-point ancestors, linked files and hard links. During an output write,
the repository and output-parent components stay open without delete sharing so
a concurrent rename cannot redirect the new file.

## Windows filesystem behavior

- Directory enumeration is bound to open directory handles and uses NTFS file
  IDs. Files are opened without following their final reparse point, checked
  against the enumerated file ID, and checked by final handle path against the
  reviewed root before bytes are read. Every root-path component is checked by
  final handle name, preventing junctions or symbolic links in ancestors from
  redirecting discovery. Source bytes and the bounded traversal are rechecked
  in a second pass.
- Relative report paths preserve the names returned by NTFS and use `/`
  separators. Exclusion globs and standard ignored-directory names match
  case-insensitively. If two names in one directory collide under case folding,
  discovery returns an `incomplete_analysis` report with
  `case_ambiguous_directory_entries` instead of choosing one.
- The compatible report `mode` field reflects the metadata exposed by the
  platform stat API. On Windows it primarily distinguishes the NTFS read-only
  attribute; it is not a representation of the full Windows ACL. Report output
  privacy is enforced separately with its owner-only DACL.
- File symlinks, directory symlinks, junctions, volume mount points and other
  reparse points are never followed. They produce `symlink_excluded`,
  `junction_excluded` or `reparse_point_excluded` limitations and make coverage
  incomplete. A reparse point in the repository root or one of its ancestors
  blocks the operation. External JSON input and output paths also reject
  reparse-point ancestors. Link cycles therefore cannot be traversed.
- Files with multiple hard links are excluded as `hardlink_excluded`. A file
  system that cannot provide a nonzero volume/file identity is rejected as
  `ambiguous_filesystem_identity`.
- Names that Windows would normalize ambiguously (reserved device names,
  alternate-data-stream syntax, trailing dots or spaces) are reported as
  `unsupported_path`. NTFS alternate data streams are not enumerated.
- A drive path whose final handle name differs from its normalized requested
  path, including short-name aliases, is rejected as `ambiguous_windows_path`.
- Long drive paths beyond the legacy 260-character limit are supported through
  the extended path prefix, subject to Windows and NTFS component limits.
  The fixtures cover both long files below a short root and a repository root
  whose own path exceeds 260 characters. A path beyond the supported Windows
  limit returns `long_path_unavailable` rather than a partial success.

The Windows test suite stubs the Win32 drive/volume response to assert explicit
`unsupported_unc_path` for mapped drives and `unsupported_windows_filesystem`
for a non-NTFS volume. It does not claim a live ReFS or network-share test.

The broader repository-session filesystem, placement selection/conclusion,
executable integration lifecycle, native isolation runner, provider operations
and runtime activation retain their separate platform and authorization
contracts. Windows discovery does not qualify or authorize those operations.
