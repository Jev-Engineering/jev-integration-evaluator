# Offline source-matched review drafting v1

`jev_integration_evaluator.agent_review` is a read-only preparation boundary.
`retrieve_context(root, reviewed_inventory, candidate_id)` reads files named
by the inventory and checks their hashes before returning bounded source,
symbols and role hints. It also scans at most 5,000 nearby paths for relevant
callers, tests and host policy files; included bytes have individual hashes.
The default limits are 24 included files and 120,000 source bytes. It does not
import a target module. Context contains source text and must
remain in a private local artifact; it is not suitable for a public log or PR.

`draft_reviewed_spec(root, inventory, context, RecordedReviewAdapter(proposal),
saved_answers=..., trusted_verification=...)` accepts a strict recorded offline
proposal. The proposal must include `schema_version=1.0`,
`kind=offline-agent-review-proposal-v1`, the SHA-256 digest of the exact request,
reviewer, reason, source evidence references, recipe ID, existing binding names,
Choice/Noul questions, primary/evidence roles, exhaustive label actions and an
`unresolved` string list. The exact request is:

```text
{context, saved_answers,
 authority: {mutation:false, execution:false, egress:false,
             installation:false, activation:false}}
```

The reviewer cannot supply verification cases, host policy, runtime ownership,
approval or execution scope in its proposal. `saved_answers.host_policy` and
`saved_answers.runtime_ownership` are caller-owned; `trusted_verification` is
independent of the reviewer. Missing inputs yield `unresolved` fields. The
reviewer response must use exactly the declared fields; extra command,
authority, measurement or source replacement fields fail closed. A changed
source, answer or context invalidates `request_sha256`.
The adapter may report only `ambiguous_callback`, `missing_independent_observation`,
`unsupported_binding` or `missing_host_capability` as blocked facts. It cannot
invent additional questions. Only absent caller-owned host policy, runtime
ownership or independent verification appears in the `unresolved` result.

The proposal schema is mirrored at `schemas/offline-agent-review-proposal-v1.schema.json`
and `jev_integration_evaluator/data/offline-agent-review-proposal-v1.schema.json`.

On a complete draft, the existing specification and inventory validators run,
then the recipe transformer parses existing callbacks and registered actions
without writing target files. Its output is discarded after qualification. The
result contains a reviewed specification and separate source/proposal digests.
This is semantic/binding review evidence, not mutation, execution, installation,
provider, or activation authority. The generated runtime configuration must be
off. The offline adapter is the only accepted adapter; remote source transmission
requires a separately implemented and explicitly scoped egress boundary.

Current support follows the existing recipe transformer: a flat Python module
with a single synchronous tail call and unambiguous supported bindings. Missing
host callbacks, independent observations or policy are unresolved; the reviewer
cannot create replacements. Tests use synthetic fixtures, including renamed
opaque callback identifiers and a POSIX discovery-to-specification path. They do
not establish live benefit or target safety.
