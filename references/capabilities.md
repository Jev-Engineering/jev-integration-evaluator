# Source capability discovery and nominations

Status: **dev4 discovery contracts retained in 1.3.0.dev6**.
The integrated read-only discovery contract is available through the central CLI
and standalone module/script. The [dev5 inventory/semantic-review bridge](repository-discovery-v1.md)
uses these contracts. A complete source-reviewed no-useful-placement outcome
was completed by the later dev8/dev9 bounded review contracts. The repository
implementation roadmap remains open. Discovery preserves the existing scanner,
recipe, review, optimizer, lifecycle, runtime, receipt and safety validators.

## Commands

Run from a checkout containing this package and its existing declared jsonschema
dependency, or from an installation containing the module and its data files:

```text
python -m jev_integration_evaluator discover-capabilities --repo TARGET --out NEW_EXTERNAL_REPORT.json
python -m jev_integration_evaluator nominate-candidate --repo TARGET --nomination NOMINATION.json --report-sha256 EXTERNALLY_RETAINED_REPORT_SHA256 --out NEW_EXTERNAL_NOMINATION.json
python -m jev_integration_evaluator.capabilities discover --repo TARGET --out NEW_EXTERNAL_REPORT.json
python scripts/discover_capabilities.py discover --repo TARGET --out NEW_EXTERNAL_REPORT.json
python -m jev_integration_evaluator.capabilities nominate --repo TARGET --nomination NOMINATION.json --report-sha256 EXTERNALLY_RETAINED_REPORT_SHA256 --out NEW_EXTERNAL_NOMINATION.json
```

An optional `--policy EXTERNAL_POLICY.json` accepts bounded settings and explicit
exclusions. It must be outside the target. The policy is part of the report
identity. Target AGENTS.md/configuration and nomination text cannot change it.
The caller's explicit policy is not an execution or mutation approval.

Outputs must have an existing directory outside the target. They are created
exclusively, never overwrite an existing file or link, and are private to the
caller: POSIX uses mode 0600 and native Windows uses a protected owner-only
DACL. The POSIX writer also fsyncs the parent directory. The CLI emits only a
digest/status or a stable redacted error class. These private metadata reports
may contain source paths, qualified names and untrusted nomination rationale.
They must not be published as private-target evidence without separate
disclosure review.

Native Windows checks every repository-root, external JSON-input and output
directory component by its final handle path. Reparse-point ancestors cannot
redirect these operations; linked JSON inputs and hard links are rejected.

Exit code 0 means the requested artifact was written, not that the target is
eligible or verified. Inspect `discovery_outcome` or `status`. Exit code 2 means
a blocked/invalid operation. There is no execution option, provider option,
activation flag or shell-command adapter.

## Read and identity contract

Discovery and admission use descriptor-relative, no-follow reads on supported
POSIX systems and handle-bound traversal on qualified native Windows NTFS
volumes. Windows drive-letter roots use NTFS file IDs and explicit reparse-point
checks; UNC/mapped paths and non-NTFS volumes are rejected. The three CLI
contract-validation input paths use the same secure artifact readers. Every
absolute directory component is checked without following links. Source
traversal is bounded by entry, file, byte, depth, symbol and AST-node limits.
Known nonregular files are rejected before opening; replacements are rejected
using type and identity checks. Hard links and links/reparse points are
excluded. Source bytes/modes and bounded enumeration are checked twice. Source
text is not imported, compiled to bytecode, executed, returned in the report or
sent to a provider. Parsing builds an AST only.

The report binds the POSIX root's device/inode/path identity or the Windows
NTFS volume/file identity, current bounded source/configuration hashes and
modes, caller policy, parser major/minor identity, and hashes of the module plus
all three schema files. It is deliberately
not a complete repository snapshot: Git internals, ignored/generated directories,
unsupported file extensions and caller exclusions are not hashed. A Git clean
status, atomic filesystem snapshot, installed dependencies or execution isolation
is not inferred. A later mutation must still run the existing complete plan and
receipt validators. Hashes do not authenticate a maliciously replaced engine or
act as semantic approval.

AST-node limits are checked after bounded-size parsing. These limits and careful
file access are not a process memory sandbox. Discovery executes no target code
and does not satisfy issue #8. Hostile same-privilege processes able to replace the
installed evaluator or move entire directory hierarchies are outside this
preparation contract; use a trusted/appropriately isolated development environment.

## Discovery is not suitability or implementation support

All Python function definitions are inventoried with qualified names, full-file
SHA-256, AST SHA-256 and line anchors, irrespective of opaque identifiers.
Unambiguous literal registries are reported as possibilities, never trusted host
policy. A narrow `module-tail-call-v1-preflight` label checks only structural
prerequisites; it is **not** `module-tail-call-v1` recipe acceptance. In particular,
full callback/registry, source scope and runtime policy checks remain with the
existing engine. Other shapes retain `unsupported_or_unresolved`.

Known deterministic-operation shapes and externally declared hard-real-time
seams are ineligible. Nominations cannot override them. The deterministic check
is conservative and not whole-program purity or equivalence analysis; semantic
review is still mandatory for unknown cases. Ambiguous symbols, definition-time
rebinding, changed bytes/modes/policy, unknown anchors, excluded paths, stale
AST/line/source hashes and missing supporting evidence reject admission.

A strict nomination specifies the report digest, seam identity, source anchors,
A–M pattern hypothesis, proposer, rationale and source-hashed evidence. Admission
returns a new source-bound record with `nominated_pending_semantic_and_binding_review`,
`benefit: null`, `execution_qualified: false`, and all authority fields false.
The model/proposer's name is retained as data, not authenticated reviewer identity.
This record is **not yet a legacy opportunity inventory entry or implementation
specification**. Automatic inventory admission, scoring/review integration and
reviewed-spec preparation are remaining work; callers must not manufacture a
legacy inventory by changing these status fields.

## Outcomes and coverage

| Outcome | Meaning |
| --- | --- |
| `no_candidates_discovered` | No function candidates found in the bounded source set; not proof of no useful placement. |
| `deterministic_rejection` | All discovered candidates match mandatory ineligibility rules. |
| `unsupported_or_unresolved` | No eligible seam established the limited structural preflight. |
| `review_required` | At least one possible preflight seam still requires semantic/binding review. |
| `incomplete_analysis` | Limits, unreadable/excluded special paths or unavailable/unrequested parsers prevent complete in-policy analysis. |

Flat Python, regular-package, src-layout and namespace-or-directory sightings
remain separate. Packages/methods/async/decorators do not inherit flat-module
rewrite qualification. Discovery does not call the optional trusted TypeScript
parser: JS/TS and other-language files are explicitly unparsed and keep analysis
incomplete. The original scanner's parser support remains unchanged. Test/config
sightings are not proof of installed environments, successful tests, callable
host policy, valid locks, independent observations or useful placements.

There is intentionally no `no_useful_placement` semantic conclusion at discovery.
Issue #7's selection contract and source-matched semantic review must establish
such a result. Unknown measurements, egress scope and spending bounds are never
invented here.

## Qualification and remaining work

`tests/test_capabilities*.py` cover discovery, adversarial inputs, source-linked
examples, main CLI validation and installed-package discovery/admission. The host
fixtures are assistant-authored synthetic examples, not the independent issue #9
corpus. Historical JSON examples bind their recorded parser identity; AST hashes
are not portable across Python versions. Fresh per-interpreter checks recompute
anchors, reports and admissions from actual source bytes.

The central `validate --kind` command recognizes `repository-capabilities`,
`candidate-nomination` and `admitted-nomination`. Contract validation does not
re-read the target, certify an engine, or establish current source suitability.
Its secure artifact reader has the same POSIX requirement and rejects special,
linked or oversized input files. Use `nominate-candidate` for fresh
source/policy/report checks.

See [`platform-support.md`](platform-support.md) for the native Windows discovery
qualification and filesystem limits. The broader repository-session/runtime
contracts retain their own platform restrictions. New-language rewriting,
independently authored host qualification, provider connectivity and application
benefit remain unestablished. The nominal structural preflight does not authorize
any rewrite. The dev5 bridge constructs a real source-matched inventory and
applies semantic review with eligibility gates intact. Issue #5 remains open for
a complete source-reviewed no-useful-placement outcome; dev4 qualification
remains historical in `validation/DISCOVERY-VALIDATION-1.3.0.dev4.md`.
