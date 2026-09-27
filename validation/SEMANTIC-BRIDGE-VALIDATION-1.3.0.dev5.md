# 1.3.0.dev5 semantic bridge integration qualification

Executed local qualification on 2026-09-27. Hosted CI and merge readback are
separate publication gates; these local results do not claim their completion.

## Supplied checkpoint and integration base

Input: `JEV_Discovery_Partial_Checkpoint_34c79d46.zip`, SHA-256
`6e94f26145e4cc7ac29ad3c4aef14271a5949c54ba141063fba9f6da44fecdd2`.
All 66 payload entries matched the supplied manifest and exact payload file set.
The 12 baseline files matched their Git objects at `34c79d46` (dev3).
Its patch SHA-256 was
`47311dd0c469276381d7e767e5ede3bd5dad90f932a43b5d71c912ae3c447ea7`.

Integration starts at `de2be75c5eb84874de3a9167342ea2c0134a556b`
(merged PR #18, dev4), retaining all earlier fixes and contracts. The supplied
alternate discovery implementation was not adopted. Review reproduced 18 failures
in that implementation, including source/mode drift, symlink traversal and
incorrect shape/exclusion hints. The bridge now delegates to the hardened dev4
engine. Those discarded probe tests are not counted as delivered tests.

## Integration corrections

- Apply source capability exclusions to heuristic candidates as well as nominated
  candidates. The hard-real-time bypass was reproduced before the fix.
- Withhold missing or ambiguous capability seams from the legacy inventory.
- Bind preparations to source/mode/root/policy/parser and bridge engine identity;
  bind reviews to preparation and candidate source digests.
- Keep candidate runtime off; reject review fields that add estimates, binding
  approval, executable operations or authority.
- Register the stages and three structural validation kinds in the installed CLI.
  Require private external output, redact diagnostics and reject linked input.
  Symlink-loop diagnostic leakage was reproduced and fixed.
- Preserve dev4 APIs and schemas; add three strict mirrored bridge schemas and six
  source-linked synthetic record examples. No new dependency or provider added.

## Evidence limits

The new discovery/review stages execute no target code. Installed-wheel planning
proves data compatibility with the existing C recipe, not applied host wiring.
The older A–M demonstration executes synthetic hosts with injected test runtime;
it establishes neither a provider connection nor production activation/benefit.
The demo's source-matched negative semantic opinion is assistant-authored; it is
not independent corpus qualification or a whole-repository absence proof.

Issue #5 remains open for a complete source-reviewed no-useful-placement outcome.
The broader session command, authority model, corpus and roadmap remain separate
open work. Native Windows discovery is unsupported; local Linux checks without
Node do not establish TypeScript-enabled or hosted matrix success.

## Executed qualification

A byte-matched isolated native Linux copy was tested under Ubuntu Python 3.12.3,
pytest, PyYAML, jsonschema and setuptools. No Node/TypeScript parser was available
in that local environment. Logs and exact input hashes were retained outside the
source checkout.

| Check | Result |
|---|---|
| Full `python -m pytest -q` | 952 passed, 4 skipped (three native-Windows-only checks and one unavailable optional trusted TypeScript parser) |
| `validate_package.py --check-manifest` | 34 mirrored schema pairs; 684 exact release manifest entries; 321 synthetic research records; 13 implementation examples; 3 discovery and 6 bridge examples; one observation and one offline replay |
| Installed-wheel coverage (included in full suite) | Existing implementation/discovery wheel suites plus two new installed bridge tests; opaque nomination reaches source-matched semantic review; a separate synthetic C fixture reaches existing plan generation without target execution or modification |
| v1.1 and v1.2 offline demos | Passed; synthetic evidence remains ineligible for activation |
| A–M implementation demo | All 13 passed; 21 baseline and 63 modified cases; all target bytes restored |
| Discovery/review demo | Eight private records; source-matched negative synthetic opinion; no target import/execution or network request |
| Native Windows Python 3.14.3 CLI checks | 5 passed, 35 skipped for POSIX-only paths; this is explicit unsupported-platform coverage, not Windows discovery qualification |
| Native Windows release-fixture checks | 4 passed after fixing the current validation-record requirement |

The first full integration run had 951 passes and one release-fixture failure:
the package validator still required the historical dev4 validation record when
the fixture copied only the declared current record. Correcting that requirement
produced the passing full run above. The validation record, documentation and
manifest were then finalized. Source, schemas, examples and tests match the
qualified native snapshot except for CRLF-to-LF normalization in the stage CLI
and demo files. Final package/manifest validation is repeated after those edits;
hosted CI qualifies the exact published commit.

Independent agent review identified and checked the all-candidate eligibility
fix, source-reader guards, private CLI output and symlink-loop diagnostics. It is
internal implementation review, not the separately authored issue #9 corpus or
authenticated semantic approval. The CI workflow retains Python 3.10/3.12/3.13
with trusted Node/TypeScript, a Python-only job, installed-wheel tests and all
demos. Actual hosted results must be read from the corresponding PR/run.
