# Platform support matrix

This matrix separates the read-only `repository-discovery` contract from
repository sessions, implementation planning and runtime operations. A discovery
report is a bounded source snapshot; it is not an execution sandbox or a global
absence proof.

The `javascript.recipe-c@1.0.0` catalog entry declares Linux x86-64 with a
trusted external Node executable and TypeScript 5.8.3 compiler. Its present
qualification includes source-bound planner materialization, scoped offline
npm installation and supervised normal package commands for ESM, CommonJS
and TypeScript in synthetic off-mode fixtures. The installed evaluator CLI
journeys ran in [PR #99](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/99)
and [PR #104](https://github.com/Jev-Engineering/jev-integration-evaluator/pull/104);
[the #104 merge run](https://github.com/Jev-Engineering/jev-integration-evaluator/actions/runs/36642699747)
passed. A separate installed connected owner exercises synthetic shadow
sessions in local offline fixtures. Its dedicated exact Node 24 CI gate
requires the final combined revision to pass on a hosted runner. Provider
reachability and observed canary/active qualification remain pending.
Windows Node interop does not qualify native Linux execution.

The separate generated Python adaptation runtime profile has local offline
Windows qualification for regular and `src/` package wheels through their
installed console commands on the current interpreter. It exercises off and
synthetic shadow for method, async, and fixed-positional seams. This does not
qualify native isolation, Linux/WSL behavior, connected async routing, or live
benefit; see `references/python-adaptation-runtime-v1.md`.

The separate [delivery session v1](template-delivery-session-v1.md) has an
offline installed-console profile only for Linux x86-64 CPython 3.13 with an
owner-private environment and external observation files. Windows, macOS,
other Python versions, service managers, connected provider activation and
generic container or cloud delivery are not qualified by that profile.

The proposed [native Windows template preparation](windows-template-preparation-v1.md)
checks selected reviewed file bytes and local NTFS paths without changing the
host. It is not native template delivery. Current stage support is:

| Native Windows stage | Current qualification |
| --- | --- |
| Repository discovery | Qualified only as recorded below. |
| Selected source/path preparation | Read-only local Windows 11 Pro build 26200, CPython 3.14.3 observation; also exercised in the separate Server 2022 off-mode suite described below. |
| Selected package-input inventory | Read-only local Windows 11 Pro build 26200, CPython 3.14.3 observation, also exercised in the separate Server 2022 off-mode suite. It checks reviewed files in its declared traversal and selected wheel bytes, reports skipped directories, and grants no build/install authority. |
| Implementation planning (no target effect) | `make_patch_plan` and `plan_implementation` run on local NTFS without changing the host: a plan naming two case aliases is refused and leaves the directory empty (`test_native_case_alias_duplicate_plan_refused`), and the installed delivery fixture plans, baselines, applies and re-verifies its reviewed implementation before packaging (`test_native_offline_package_install_and_normal_console`). A plan grants no mutation authority. Plan creation refuses a read-denied or exclusively locked target with the path-free `windows_source_read_access_denied` (`test_native_read_denied_source_refuses_plan_with_private_reason`, `test_native_exclusively_locked_source_refuses_plan_with_private_reason`) and an on-disk case alias in a per-directory case-sensitive tree with `windows_source_case_alias_refused` (`test_native_real_case_alias_refuses_plan_without_effect`). With a read-denied selected source, `plan_implementation`, `implementation_status`, `apply_implementation`, `rollback_implementation`, `verify_implementation` and binding preparation stop before any write but still raise the raw `PermissionError` containing the path. No native test plans against an unsupported root. |
| Source mutation (apply and rollback) | A separate reviewed `apply_patch_plan` local NTFS source-mutation component has native Windows 11 CPython 3.14.3 fixture coverage for exact approved bytes, protected and inherited owner/DACL preservation, owned rollback, concurrent same-content replacement refusal, read-only/hardlink/locked-file refusal, case aliases and a long path. A deny ACE on the write path (new entries denied on the parent directory, or `DELETE` on the file together with `DELETE_CHILD` on its parent) refuses the apply with unchanged bytes, file identity and directory entries and no external intent (`test_native_write_path_acl_denial_refuses_apply_without_effect`). A deny ACE for file data reads refuses with the path-free `windows_source_read_access_denied` and no effect (`test_native_read_denied_source_refuses_apply_with_private_reason`). A file whose inherited DACL was marked auto-inherited by an `icacls` add and remove, on the file or its parent, is applied and rolled back with identical owner, DACL bytes and policy bits (`test_native_icacls_touched_inherited_dacl_is_reproduced_exactly`); a descriptor Windows does not reproduce stays refused as `windows_source_acl_not_reproducible`. This does not qualify the complete native template-delivery journey or Windows Server. See [source mutation](windows-source-mutation-v1.md). |
| Repository session journal (`repository-session-v1`) | POSIX journal contract; native Windows unsupported. A code guard in `repository_run.Journal` rejects a non-POSIX host with `unsupported_session_filesystem`; no native Windows test exercises it. This row is not the template session supervisor described two rows below. |
| Package build and install | Separate native offline API checkpoint ran on Windows 11 Pro build 26200, CPython 3.10.11, 3.13.13 and 3.14.3 on NTFS, and in the Server 2022 off-mode suite below; it binds reviewed applied source and hash-locked wheels. Each local interpreter has a retained private receipt archive. A 3.14.3 test also rejects dangling NTFS junctions at prospective package/install roots before status or replay. Broader source-filesystem and recovery additions require separate evidence. The #55 installer remains Linux only. |
| Template session supervisor: normal console launch, observation and owned stop | Native API checkpoint ran installed off-mode consoles locally and in the Server 2022 suite under a gated Job Object, with separate entry-ready and effect observations, exact owned stop, and retained 1.0.0 → 1.0.1 → 1.0.0 selection in one run. The offline `windows_template_session` supervisor is qualified for exactly this: one launch per recorded session of an anchored off-mode install; a gate, named Job and guardian (`test_guardian_retains_named_job_and_kills_owned_gate_on_exit`); exact-identity stop that leaves an unrelated process alone (`test_owned_job_stop_does_not_touch_unrelated_process`); retained `blocked_recovery` after an interrupted launch (`test_native_interrupted_launch_retains_identity_and_refuses_replay`); a refused replay that leaves the Job's member set and launch records unchanged (`test_native_refused_replay_leaves_owned_job_members_unchanged`); refusal of status, new sessions and launch after installed `config.json` content drift (`test_native_install_config_content_drift_blocks_status_session_and_launch`) and after a byte change that parses to the same configuration (`test_native_install_config_byte_drift_blocks_status_session_and_launch`); and a console break delivered on the owned console, reported as `exited_unverified` with no surviving Job member, no effect record and an untouched unrelated process (`test_native_console_break_cancellation_leaves_no_owned_process`). Not qualified: a cancellation API (the break is an external event the supervisor only observes), relaunch or resume after an uncertain launch, interactive standard streams, service managers, abrupt supervisor death, machine power loss, target isolation and any provider-connected mode. This is synthetic fixture evidence; the #56 delivery session remains Linux only. |
| Unsupported roots: source/path preparation | A UNC or extended UNC source root or output parent returns `windows_preflight_unsupported_unc_path` through the API and the preflight command; a mapped-drive answer returns the same reason and a non-NTFS or non-disk answer returns `windows_preflight_unsupported_windows_filesystem`, with no file written (`test_native_unc_mapped_and_non_ntfs_roots_are_refused_without_effect`). |
| Unsupported roots: package-input inventory | Each of host root, wheelhouse, package output parent and environment parent is refused as UNC or extended UNC with `windows_package_unsupported_unc_path`; mapped and non-NTFS answers return that reason or `windows_package_unsupported_windows_filesystem` (`test_native_unsupported_roots_are_refused_for_every_package_input`). |
| Unsupported roots: package planning/build and install planning/install | Package planning refuses a UNC host root, wheelhouse, output parent, environment parent, implementation bundle or template directory. With a mapped or non-NTFS volume answer, package planning and build return the `windows_package_` reasons above, and package status, install planning, install and install status return `windows_owned_generation_parent_unavailable`; no environment generation is created and the built package generation is unchanged (`test_native_unsupported_roots_block_package_and_install_planning_without_effect`). Source mutation, session creation and launch have no dedicated unsupported-root test. |
| Unsupported roots: evidence boundary | UNC spellings are real `\\localhost\C$\...` paths refused before any open. Mapped-drive and non-NTFS cases replace only the Win32 drive-type and filesystem-name answers; no live network share, mapped drive, ReFS, FAT or exFAT volume was exercised. |
| Case-colliding source names | In a real per-directory case-sensitive NTFS directory (`fsutil file setCaseSensitiveInfo`, no elevation on the local host), two names differing only by case are refused by the package-input inventory for either single reviewed spelling and for both, and by the installed-tree inventory (`test_native_real_case_colliding_source_names_are_refused`). Selected-file preparation refuses a reviewed file or directory component that has such a sibling with `windows_preflight_case_alias_refused` (`test_native_real_case_alias_blocks_selected_source_preparation`), and `apply_patch_plan` refuses an update of either spelling, or a creation beside a differently cased entry, with `windows_source_case_alias_refused` and no effect (`test_native_real_case_alias_refuses_apply_without_effect`). `make_patch_plan` refuses the same spellings with the same reason before reading the target (`test_native_real_case_alias_refuses_plan_without_effect`). All three reuse the inventory's case-folded comparison. An alias created after the check is not detected. |
| Locked package inputs and installed generations | A handle that shares nothing on a reviewed wheel or reviewed source file refuses package planning, build, install planning and install with `windows_package_access_denied`; on the built host wheel it refuses install planning and install with `windows_package_status_unavailable`. Each refusal creates no generation. A lock that arrives after the build intent fails the offline tool install with `windows_package_offline_command_failed`; the retained partial generation reports `blocked_recovery` and refuses replay, also after the handle is closed, while a separately reviewed output parent then builds, installs and runs one supervised off-mode console (`test_native_locked_package_inputs_block_build_and_install_fail_closed`). A locked file inside the selected generation, or inside the generation an upgrade would select, refuses the upgrade, and a locked file inside the retained generation refuses the rollback, each with `windows_install_status_unavailable` (`windows_owned_record_unavailable` for a locked retained install receipt); no stage intent, generation, selection or child session is recorded, the previous selection is unchanged, its generation runs one supervised off-mode console after the handle is closed, and the same upgrade and rollback then succeed (`test_native_locked_generation_file_blocks_upgrade_and_rollback_selection`). A lock taken after a check has passed, a lock on a directory, byte-range locks and antivirus or indexer handles are not exercised. |
| Generation write-path ACL denial | A deny ACE for new subdirectories on the package output parent or environment parent fails the build or install with `windows_owned_directory_create_failed` and creates nothing. A deny ACE added to the exclusively created install generation before its first owner record fails with `windows_owned_directory_changed`; the retained directory then blocks status and replay, including after the ACE is removed (`test_native_generation_acl_denial_blocks_build_and_install_fail_closed`). |
| Verification and execution isolation | No Windows seccomp-equivalent target isolation in this profile. |
| Provider-connected runtime | Pending independent authority and live qualification. |
| Synthetic connected shadow profile | Offline only. The [installed connected shadow](windows-template-connected-v1.md) fixture uses a local TLS endpoint, a synthetic issuer and synthetic responses and effects (`test_native_connected_installed_hard_block_and_replay`, `test_native_cng_checks_exact_p256_message_without_issuer_key`, `test_native_scope_requires_exact_signature_and_live_expiry`). No provider credential or live endpoint is supplied; it does not move the row above out of pending. |

The separate native off-mode suite passed 31 cases with zero skips on
Windows Server 2022 build 20348, CPython 3.10.11 and 3.13.15, in the
[PR #106 actual merge-commit run](https://github.com/Jev-Engineering/jev-integration-evaluator/actions/runs/36647200079)
at `a7c0b025612f1fbb3a0cb7e1721773316db4821b`. This is distinct from discovery
qualification and does not establish later interruption additions, arbitrary
source mutation, untrusted execution, provider operation or measured benefit.
The later 38-case native suite, including controlled launch/install interruption
and owned installer-process death, passed on both Server interpreters with zero
skips in the [PR #110 merge run](https://github.com/Jev-Engineering/jev-integration-evaluator/actions/runs/36669705064)
at `1aff22197d0ff5c64b660544b77ed81e1ab310bc`. It does not establish machine
power-loss durability, broader source mutation or provider qualification.
The issue #61 gap additions named in the table above bring the scheduled
`windows-template-delivery` selection to 80 cases, which is now its required
minimum. The nine added cases passed locally on Windows 11 Pro build 26200,
CPython 3.14.3, without elevation. Their Windows Server 2022 execution is
not yet recorded; in particular, per-directory case sensitivity and console
attachment on the hosted runner are unverified until that job runs.
The four issue #61 findings fixed afterwards (exact installed configuration
bytes, a path-free read-denied apply refusal, on-disk case aliases at
preparation and apply, and exact reproduction of an auto-inherited DACL) add
six cases, so the selection and its required minimum are now 86. Those six
passed locally on Windows 11 Pro build 26200, CPython 3.14.3, without
elevation; their Windows Server 2022 and CPython 3.10/3.13 execution is not
yet recorded.
The plan-refusal and locked-file follow-up adds five cases, so the selection
and its required minimum are now 91. On Windows 11 Pro build 26200, CPython
3.14.3, without elevation, the three plan cases passed and the package-input
lock case passed once. The upgrade and rollback lock case has no complete
passing run recorded: its only full local run reached the last rollback lock
and failed there on a test expectation that was then corrected, and the
repeat run was stopped by the host for low memory. Its qualification, the
repeat of the package-input case and all Windows Server 2022 execution of the
five cases are pending. The `windows-template-delivery` matrix now
also schedules CPython 3.14 beside 3.10 and 3.13. Hosted 3.14 delivery
qualification is pending until that job's first run completes: no hosted
3.14 delivery result exists yet, and the hosted 3.14 evidence recorded so far
is only the separate `windows-connected-shadow` job.

| Platform and filesystem | Repository discovery | Qualification |
| --- | --- | --- |
| Linux, including WSL2 Linux filesystems | Supported through POSIX descriptor-relative reads with `O_NOFOLLOW`. | Existing Linux CI and recorded Linux/WSL runs. This change does not restart or reconfigure WSL. |
| macOS with the required POSIX descriptor operations | Existing backend retained. | No macOS runner was added by issue #42; current macOS versions are not newly qualified here. |
| Windows 11 Pro build 26200, CPython 3.14.3, local NTFS drive | Locally qualified for the dedicated discovery fixtures and source-bound preparation. | All 19 dedicated tests pass. This account cannot create real symbolic links, so hosted CI covers actual file and directory links. |
| Windows Server 2022 hosted runner build 20348, NTFS, CPython 3.10.11 and 3.13.15 | Qualified for native repository discovery on local drive-letter roots. | The `windows-discovery` jobs pass all 19 tests on both interpreters with zero skips, including real symbolic links and junctions, ACL denial, long paths, UNC outcomes, and interruption. Separate native off-mode delivery evidence is recorded above; discovery alone does not establish it. |
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
being considered. CI enables Developer Mode to create symbolic-link test
fixtures; this is a test-runner setup and is not required by the scanner. A
denied source file or directory is recorded as an
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

Reviewed source mutation on a supported local NTFS path has an additional
handle-bound contract described in [Native Windows reviewed source mutation](windows-source-mutation-v1.md).
Its private recovery intent is stored outside the approved source tree. A
same-content peer replacement, unknown file identity, or changed ACL refuses
rollback; Windows symlink and junction coverage requires native runner evidence.
