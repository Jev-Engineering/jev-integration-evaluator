# Repository discovery and semantic review

Version 1.3.0.dev5 introduced three read-only stages of issue #5. The later
`conclude` stage is specified separately in
[`repository-conclusion-v1.md`](repository-conclusion-v1.md). They use the
published dev4 discovery engine and the existing scanner/scoring constructors.
They do not implement issue #4's durable repository implementation session.

## Commands and data contracts

Run the trusted evaluator installation, using paths as data. Every output must
be a new file in an existing, caller-owned directory outside the target. Output
files are created exclusively with mode 0600; stdout contains only a status and
digest. Failures return a redacted reason with exit status 2. A success status
does not establish host wiring, provider connectivity or activation authority.

```bash
jev-integration-evaluator repository-discovery REPO --out CAPABILITIES.json
jev-integration-evaluator repository-discovery REPO --stage prepare --capabilities CAPABILITIES.json --nominations NOMINATIONS.json --out PREPARED.json
jev-integration-evaluator repository-discovery REPO --stage review --capabilities CAPABILITIES.json --prepared PREPARED.json --review REVIEW.json --out REVIEWED.json
```

`python -I scripts/prepare_repository_inventory.py` exposes the same stages.
`NOMINATIONS.json` is an array of existing `candidate-nomination` records with
report digest, seam ID, exact source anchor, A–M pattern, proposer, rationale and
source-hashed evidence. Preparation embeds existing `admitted-nomination`
records and the unchanged `opportunity` inventory contract.

Three new strict schemas are mirrored under `schemas/` and package `data/`:
`repository-nominated-inventory-v1`, `repository-semantic-review-v1`, and
`repository-reviewed-inventory-v1`. The central `validate --kind KIND --input
FILE` command supports all three. Validation checks shape only and reports
`source_revalidated: false`; only a fresh prepare/review invocation rechecks
the source. The existing discovery/nomination contracts and commands remain
available as documented in [capabilities.md](capabilities.md).

`--config` accepts a complete evaluator configuration as external JSON data.
`--policy` accepts external JSON with the published `DiscoveryPolicy` fields:
bounded file/entry/AST/report limits, exclusion globs and hard-real-time selectors.
No target-owned configuration is implicitly loaded. Repeat the same external
configuration and policy at every stage; input reports cannot supply authority
to relax them. Configuration exclusions are unioned into the discovery policy.
Defaults intersect evaluator bounds; explicitly looser bounds are rejected.

The bare `discover-capabilities` default file limit is 1,048,576 bytes; the
evaluator-aware default is 1,000,000. Begin with `repository-discovery` for this
pipeline. Older reports require matching externally supplied bounds/configuration
or a rescan. Reports from different effective policies are not interchangeable.

## Preparation and semantic review

Preparation recomputes the report from current source, admits source-matched
nominations, and reuses `_python`, `_patterns`, `build_architecture`, `discover`,
`analysis_identity` and existing candidate constructors. Nominated candidates
start `review_required` and semantically unapproved. Benefit estimates remain
unknown and candidate runtime policy remains off, even if external configuration
requests active mode. The command does not invoke the target or provider.

Deterministic and hard-real-time exclusions apply to **all** candidates,
including those discovered heuristically without a nomination. Ambiguous or
unadmitted scanner symbols are withheld with coverage evidence. Nominations
cannot create an eligible candidate by bypassing those checks.

A review has `schema_version: "1.0"`, the exact `prepared_sha256`, and a `reviews`
mapping keyed by candidate ID. Each entry requires `source_sha256`, `reviewer`,
`reason`, and a boolean `approved`. Optional `deterministic_alternative` may only
be `preferred` or `mandatory`; optional `hard_real_time` may only be true. A review
cannot approve an already excluded candidate. Before calling the existing
`apply_reviews`, the bridge rejects estimates, score overrides, executable
commands, replacement code, binding approval and authority fields.

The reviewed envelope contains the legacy inventory under `inventory`. It can be
used with the existing planning interface after the caller supplies its separate,
source-matched binding specification and policy choices. A positive semantic
opinion alone is insufficient: mandatory host callbacks/registries, supported
source shape, exact bundle review, baseline and execution scopes still apply.
See [executable-integrations.md](executable-integrations.md).

Preparation and review bind the report, complete file snapshot, effective policy,
parser identity and hashes of bridge code, constructors and schemas. They recheck
files/root identity, bytes and modes before returning. Changed source, policy,
configuration or relevant analyzer implementation invalidates prior preparation.
These are repeatedly checked bounded snapshots, not atomic filesystem transactions.
Digests and reviewer names do not authenticate a principal. Caller-owned trusted
anchors and genuine review remain necessary; issues #4 and #6 cover session scope.

## Coverage and limitations

The qualified filesystem backend is Linux/POSIX descriptor-relative access with
no-follow traversal, regular-file checks, hardlink rejection, bounded reads and
identity rechecks. The new path explicitly fails on native Windows. Qualification
does not establish a macOS execution result or an OS sandbox.

Python AST discovery identifies flat/package/src layouts and qualified symbols.
Structural eligibility is not semantic suitability or executable support.
Rewriting remains bounded to the documented top-level, synchronous, undecorated,
single-tail-call Python shape and existing host bindings. Configuration, registry
and callback sightings are evidence for review, not verified callable bindings.

JS/TS and other unparsed sources retain their hashes and coverage limitations.
This command invokes neither target modules nor compiler configurations/plugins.
The older scanner's separate trusted TypeScript parser remains unchanged. Syntax
failures, missing parsers and exhausted budgets remain incomplete coverage.
Preparation additionally bounds nominations to 32, graph symbols to 512, graph
calls to 4096 and bridge records to 16,000,000 bytes.

Discovery distinguishes no structural candidates, unsupported/excluded shapes,
incomplete analysis and review required. **A complete source-reviewed
no-useful-placement outcome is still outstanding.** An empty candidate list or a
rejected individual candidate is not an absence proof for the whole repository.
Issue #5 remains open; this delivery does not complete the epic or other issues.

## Reproducible synthetic evidence

`python -I scripts/run_capability_demo.py --out NEW_PRIVATE_DIRECTORY` reads the
bundled opaque host and emits eight source-bound records without executing it.
The synthetic review rejects adding JEV to the fixture's keyword queue selector:
the fixture provides no observed failure or requirement justifying replacement.
This is a source-matched review example, not an independent corpus or measurement.

Full regressions, package checks, installed-wheel stages and offline demonstrations
are recorded in [the dev5 qualification](../validation/SEMANTIC-BRIDGE-VALIDATION-1.3.0.dev5.md).
No provider connection, production activation, independent semantic authentication
or measured benefit follows from these checks. No new runtime dependency is added.
