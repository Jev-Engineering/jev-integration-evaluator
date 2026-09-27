# 1.3.0.dev4 discovery integration qualification

This record covers the supplied issue #5 checkpoint integrated against main
`34c79d46f9c3c58af76f67005e35f81885258445`. It is a partial roadmap contribution.
The nomination-to-inventory/semantic-review bridge remains outstanding, and
issue #5 remains open. The repository command and other roadmap issues are not
implemented by this change.

## Input provenance

- Checkpoint ZIP SHA-256: `a8e1c8d16c6247140860db6762848c0a61c950163d05f6db034ab4921545984e`.
- Patch SHA-256: `d30c40213069744766c1329a9560ca8b2f91f52a9b1f6ae7c3e3b48aaa32e107`.
- All 35 checkpoint manifest entries matched; its embedded patch matched the
  separately supplied patch byte-for-byte. All 17 proposed paths were absent on
  current main, and `git apply --check --whitespace=error-all` passed before apply
  in an isolated worktree.
- The checkpoint's 103 passing tests and installed fragment probe used Python
  3.13.5 in a separate incomplete source fragment. They are historical evidence,
  not this integration's full-package qualification.

## Integration review

Independent agent review and fresh local tests found additional input/source
classification and cross-interpreter example failures. The integration adds
regressions and fixes, central CLI dispatch and contract validation, full-package
installed discovery qualification, version metadata and current support docs.

The initial checkpoint tests on Python 3.12 produced 100 passes and three AST
example failures. Historical examples now preserve their parser identity, while
fresh discovery/admission tests revalidate local AST anchors on every tested
interpreter. A separate 22-case input/binding/preflight regression batch produced
20 failures and two control passes before fixes, then 22 passes. Two additional
decorator regressions failed before their correction and passed afterward.
Eight further loader-bound and enclosing-scope cases passed. Final focused
discovery/adversarial/example suites: 136 passed on Ubuntu Python 3.12.3.

Independent final review rechecked shadowed/closure/decorated callees, conditional
namespace changes, generators and invalid/reserved module names while retaining
the ordinary supported structural preflight. No blocking findings remained.

## Executed integrated qualification

The complete package was copied into a native Linux temporary directory and all
661 file bytes were matched against the integration worktree before execution.
After qualification, the same file set still matched. Only this report and its
release checksum entry changed afterward; code, tests, schemas and examples did
not change.

| Check | Actual result |
| --- | --- |
| Full `python -m pytest -q`, WSL Ubuntu / Python 3.12.3 | 844 passed, 4 skipped; 64.29 seconds. Three skips are native non-POSIX rejection tests executed separately on Windows; one is the optional trusted Node/TypeScript parser absent from this local environment. |
| Installed evaluator wheel | Both the existing edited-host plan/baseline/apply/verify/rollback lifecycle and new central discovery/admission/schema CLI probe passed in fresh isolated interpreters as part of the full suite. Target import sentinel remained unexecuted during discovery. |
| `python scripts/validate_package.py --check-manifest` | Passed on Linux and native Windows: 31 schema pairs, 321 synthetic records, 13 implementation examples, 3 discovery examples, 1 observation example and 1 offline replay; all 660 manifest entries verified. |
| `python scripts/run_v11_demo.py --out NEW_PRIVATE_DIRECTORY` | Passed; synthetic threshold and study evidence remained ineligible for activation/adoption. |
| `python scripts/run_v12_demo.py --out NEW_PRIVATE_DIRECTORY` | Passed; combined-gate, shared-budget and monitoring demonstrations retained synthetic evidence and suspension-only semantics. |
| `python scripts/run_implementation_demo.py --out NEW_PRIVATE_DIRECTORY` | Passed for all 13 A–M recipes: 21 baseline and 63 modified cases; all fixture targets restored byte-for-byte. |
| Native Windows / Python 3.14.3 central CLI selection | 5 passed, 12 explicit POSIX-only skips. The three new validation kinds returned the actual unsupported-platform result; this does not qualify Windows discovery. |
| Release checksums | Rebuilt after final documentation and checked again; all code/test/schema/example bytes remain those qualified above. |

Discovery engine SHA-256:
`2a2cff1d2cfb4c671c62dc9ed6cebbef886ce05659fc8e3c36293dc2cda46cd3`.
The examples were regenerated from an actual local discovery/admission with
`cpython-3.12-ast`. Their private fixture root identity is intentionally local;
regenerate it after copying source or changing policy, parser or engine.

Python 3.10/3.13 and trusted TypeScript are not claimed as local execution. The
hosted workflow runs those environments against the published commit and now
enforces the exact checksum manifest. Its Python-only job also runs all five
discovery test files. Hosted outcomes are recorded on the PR after execution.

## Evidence limits

All example hosts and observations are synthetic. Discovery never imports target
source, runs target hooks, invokes a target parser plugin or contacts a provider.
The new contract requires POSIX descriptor-relative filesystem operations;
native Windows is explicitly unsupported. JS/TS files are reported as unparsed
by discovery; the existing scanner's trusted optional parser is separate.

Admitted nominations retain pending semantic and binding review, null benefit,
false execution qualification and false authority fields. The structural
preflight is not recipe acceptance. Existing A–M verification demonstrates
synthetic edited-host wiring; provider connection, production activation,
independent issue #9 corpus qualification and measured benefit are unestablished.

Hosted CI, signed publication and merge status belong to the linked PR and its
exact commit checks. Local results alone do not establish those outcomes.
