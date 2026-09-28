# 1.3.0.dev12 native Windows repository discovery

This qualification record covers issue #42, “Add native Windows support for
repository discovery.” It records only commands that were actually run. Local
Windows 11 discovery fixtures pass on NTFS; hosted qualification for real
symbolic links and CPython 3.10/3.13 remains pending. UNC, non-NTFS and device
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
  full Windows run is not represented as passing; supported non-Windows jobs
  must provide the integrated suite result.
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

Checksum rebuilding, hosted Linux and Windows CI, independent review, signed
publication, merge, and post-merge verification remain delivery gates. Their
results must be read from the final pull request and recorded before issue #42
is closed.
