# 1.3.0.dev12 native Windows repository discovery

This qualification record covers issue #42, “Add native Windows support for
repository discovery.” It records only commands that were actually run.
Dedicated native discovery fixtures pass locally on Windows 11 and on hosted
Windows Server 2022 with real symbolic links on NTFS. UNC, non-NTFS and device
paths return explicit unsupported outcomes. This does not qualify the wider
repository-session, placement-selection or conclusion workflows for Windows.

## Native Windows discovery fixtures

On Windows 11 build 26200 with CPython 3.14.3, the dedicated discovery suite
passed **19 tests**. Fixtures cover ordinary trees, deterministic reports,
case-insensitive exclusions, source changes, paths beyond MAX_PATH, file and
directory access denial, reparse points and junction cycles, UNC/device and
mocked mapped-drive/ReFS outcomes, output scope and parent pinning, budgets,
interruption, and the staged discovery path. This local account cannot create
symlinks, so local tests verify the fail-closed symlink classification; the
Windows CI job enables Developer Mode and requires real file and directory
symlink fixtures with zero skips.

## Hosted native Windows and Linux qualification

PR #43 workflow run [36446807669](https://github.com/Jev-Engineering/jev-integration-evaluator/actions/runs/36446807669)
passed on commit `8161411d4390399cc2f0743529df6740f0a19e2d`. The `windows-2022`
runner reports Windows build 20348 (Windows Server 2022). CPython 3.10.11 and
3.13.15 each ran `tests/test_repository_discovery_windows.py`: **19 passed,
zero skipped**. The JUnit gate confirmed 19 collected, zero skipped and zero
failures on both interpreters. The hosted job provisions Developer Mode and
long-path support so real file and directory symlinks, junction handling and
paths beyond `MAX_PATH` execute rather than skip.

The Linux full-suite jobs also passed on GitHub-hosted `ubuntu-latest` runners
with CPython 3.10.21, 3.12.14 and 3.13.15: each reported **1,740 passed, 142
skipped**. The skips are the existing environment-dependent suite cases; this
does not represent a macOS run. The supported Linux suite exercises the
retained POSIX discovery backend alongside the rest of the integrated package.

## Local integrated validation

The checks below ran on Windows 11 Pro 10.0.26200 with CPython 3.14.3
(`C:\Python314\python.exe`).

- `python -m pytest -q tests/test_repository_discovery_windows.py`: **19 passed,
  zero skipped**. The local account cannot create symbolic links, so the
  symlink classifier fallback ran here; the hosted Windows job sets
  `JEV_REQUIRE_WINDOWS_SYMLINKS=1` and fails unless real links are created.
- `python -m pytest -q tests/test_capabilities_cli.py`: **12 passed, 5 skipped**.
  The five skips are legacy POSIX descriptor and `0600`-mode fixtures; the
  Windows-specific output ACL and discovery behavior are exercised separately.
- `python -m pytest -q`: **1,200 passed, 524 skipped, 158 failed** in 298.66 s.
  The skips mainly require POSIX secure-discovery/session facilities; one skip
  requires the trusted Node/TypeScript toolchain. Failures cluster in repository
  run, selection, package lifecycle, and other workflows outside this Windows
  discovery scope, with additional POSIX-specific filesystem assertions. The
  full Windows run is not represented as passing. The Linux CI matrix above
  provides the integrated result on a supported non-Windows platform.
- `python scripts/validate_package.py`: passed; 81 schemas and 321 synthetic
  records validated, 13 implementation examples checked without execution,
  with no target code execution or network requests.
- The v1.1 and v1.2 offline demos exited 0. The implementation demo failed at
  `implement-verify` (exit 3); the capability and placement-selection demos
  returned `unsupported_secure_filesystem`; the selection demo returned
  `synthetic_demo_failed_or_output_unavailable`; the repository-conclusion demo
  returned `invalid_or_unavailable_demo_output`; and the repository-session
  demo failed with `ValueError`. These broader workflows are not qualified on
  Windows and are run on Linux by the hosted workflow.
- `git diff --check` and YAML parsing of `.github/workflows/ci.yml` passed.

The full Windows run is not a package-wide pass: only the dedicated discovery
suite is qualified on Windows. Hosted CI validates the integrated package on
Linux. For this snapshot, `python scripts/rebuild_checksums.py --write` and
`python scripts/validate_package.py --check-manifest` passed, verifying 930
release files. PR #43 still requires an independent review before normal merge;
post-merge checks and issue closure depend on that review and merge.
