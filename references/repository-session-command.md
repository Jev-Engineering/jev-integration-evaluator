# Repository session command — partial issue #4

Contract versions: `repository-session-v1`, `repository-run-context-v1`, and
`repository-run-scope-v1`, all schema version `1.0`. This is a local contribution
for issue #4, not completion of issue #4 or epic #3. The historical supplied
checkpoint was tested on an assembled source tree; this release has its own
qualification in `validation/REPOSITORY-SESSION-VALIDATION-1.3.0.dev11.md`.

## Commands and trust boundary

Path-only preparation is read-only:

```sh
python -m jev_integration_evaluator.repository_run /absolute/target
python scripts/run_repository.py /absolute/target
jev-integration-evaluator repository-run /absolute/target
```

It uses the existing bounded static discovery implementation. It imports no target
module, runs no target commands, creates no session or bundle, and grants no scope.
It reports the discovery classification rather than interpreting an empty scan as
proof of no useful placement.

Every inspection and session result also contains `next_action_contract`, a
`repository-next-action-v1` record. Its `code` repeats the existing
`next_action` string for older callers. `required_inputs` names the missing
caller-supplied evidence, `authorization` classifies the external authority
needed, `effect` describes the possible next operation, and `resume_same_run`
states whether the current session can continue. The record itself grants no
capability. Unknown codes fail closed. Incomplete path-only coverage asks for
coverage review rather than source-reviewed implementation inputs.

A path-only invocation can also consume a separately reviewed, complete source
opinion using `--capabilities`, `--coverage-review`, and independently retained
`--review-sha256`. Optional `--conclusion-config` and the context's objective and
discovery policy must match those used to prepare the review. The command calls
the existing repository conclusion verifier, which re-reads the source and
rejects drift or an unanchored review. Only its complete negative outcome yields
`no_useful_placement`; all other outcomes retain the conclusion and request
review of missing opinions. This path executes no target and creates no session.
The returned `review_principal_authenticated: false` remains explicit; digest
equality alone cannot authenticate who supplied the review.

When reviewed implementation inputs are needed, `agent_request` is a strict
`repository-agent-request-v1` record with run ID (null for path-only inspection),
repository and report identities, bounded source file hashes and modes, the
preserved objective and saved answers, and the required response contract. Its
six capability flags are all false. The compatible recorded adapter response is
now also described by the mirrored `repository-recorded-reviewed-response-v1`
schema. The opt-in `recorded-reviewed-input-v2` adapter requires a
`request_sha256` equal to the emitted `agent_request_sha256`, computed over the
complete emitted request, including run ID,
source report, context, objective and answers. Its separate mirrored response
schema requires this field. Replaying a response under a different run or
context fails before planning; source drift remains independently rejected.
The v1 four-field response stays available for existing saved reviews and
bundles. Both adapters still undergo the existing source, semantic and recipe
checks before planning. A schema-valid response cannot grant execution, egress,
installation, publication or activation.

Preparation failures are classified from explicit engine error types:
`MissingBinding` or an unavailable host prerequisite yields
`missing_prerequisite`; `UnsupportedShape` yields `unsupported`; other invalid
planning input yields `insufficient_evidence`. Each attempted plan keeps a
distinct failure code in the journal. A repository conclusion's current
`unsupported_or_unresolved` finding does not distinguish a proven unsupported
shape from an unestablished preflight, so the command conservatively surfaces
`insufficient_evidence` for that finding. A future explicit `unsupported`
support code would surface `unsupported` only with complete anchored review.
Unresolved or unanchored opinions also remain `insufficient_evidence`. The underlying
conclusion is included unchanged, and a reviewed negative explicitly reports
`review_principal_authenticated: false` at both levels. These labels do not
authenticate a reviewer or authorize a retry, effect, or deployment.

The same command accepts a caller-selected private session directory outside the
target, an optional context, recorded reviewed inputs, and a separate scope:

```sh
python -m jev_integration_evaluator.repository_run /absolute/target \
  --session /caller/private/run \
  --context /caller/context.json \
  --prepared /caller/prepared-response.json \
  --scope /caller/prepare-scope.json \
  --stop-after plan
```

The context contains an optional objective, saved answers, explicit resource
bounds, discovery policy, and either the compatible `recorded-reviewed-input-v1`
or request-bound `recorded-reviewed-input-v2` adapter.
The JSON examples deliberately grant nothing. Zero hashes and the example
reference are not authorization. Keep secrets out of inputs: use credential
references, not credentials. The caller-controlled session parent must not be
writable by an untrusted target or another untrusted principal.

V1 recorded responses have exactly `schema_version`, `adapter`, `inventory`, and
`spec` fields; V2 additionally requires the exact `request_sha256`. The existing
deterministic implementation-spec, inventory, recipe,
source, finite-label, runtime-off, and observation validators retain authority.
The adapter does not evaluate Python, commands, module identifiers or expressions
from a response. It does not implement autonomous review or draft policy and
callbacks; issue #6 remains open. Saved answers are retained verbatim, not treated
as implicit grants or automatically inferred bindings.

Planning generates a private bundle and returns its digest for review. It does
not approve its own generated diff. Supply a separately reviewed scope with that
exact digest and the externally retained returned session head:

```sh
python -m jev_integration_evaluator.repository_run /absolute/target \
  --session /caller/private/run \
  --scope /caller/reviewed-execution-and-mutation-scope.json
```

With baseline, apply and modified-verification grants, this invocation calls the
existing actual host lifecycle. Alternatively, supply an already reviewed bundle
with `--bundle` to a fresh session and authorize its exact digest; a single
invocation can then perform baseline, apply and verification. The new session
still does not gain authority from a success-shaped file inside that bundle.

`--stop-after baseline`, `apply` and `modified` expose explicit checkpoints. All
continuations use the same command and preserve the context when it is omitted.
A changed supplied objective, answer, bound, adapter or scan policy is rejected,
not silently substituted. To change the review context or accepted source, use a
new reviewed run. `--replan` accepts a changed, separately reviewed prepared
response only before any baseline, apply, modified-verification or rollback
attempt. It requires a fresh exact-head preparation scope, retains the prior
decision and bundle in append-only history, and uses a distinct private output
directory. Plan attempts remain under `max_attempts`; the maximum number of
in-run replans is one less than that bound. Interrupted replans reconcile a
finished engine plan without repeating it; incomplete private output is kept
and needs explicit bounded retry. Replanning after an effect attempt, while an
effect is pending, after cancellation, or after source/context drift is refused.
No prior bundle grant authorizes a new bundle. This is caller-reviewed replanning,
not automatic semantic drafting or a model-issued approval.

## Authorization and receipts

Scope is external to the target and independent of the agent response. The strict
scope contract identifies repository, context, bundle, caller reference, execution
classification, and individual grants. Every effectful resume checks an exact
session head retained through a caller-trusted channel. A hash read back from the
same potentially hostile journal does not authenticate that journal.

Stored authorization references record provenance but cannot authorize a later
invocation. Stored receipt hashes are usable only under an externally anchored
session, or through direct observations in the current invocation. An unanchored
read of a completed session returns `recorded_untrusted`, never `verified`.

Each completed baseline and modified-verification attempt is also copied into an
exclusive, mode-0600 private receipt archive before completing the session stage.
Copies are byte-checked and fsynced. Failed schedules remain separately addressable
when a retry replaces the core engine's current receipt. Archived names contain
only a fixed phase, bounded attempt number and content hash. Reopening the session
checks those archived bytes, their file type, ownership, link count and permissions.
Do not publish these archives or the target's source/preimages.

The journal records immutable run and repository identities, bounded source/config
hashes and modes, engine identity, reviewed input digest, objective and answers,
stage, pending intent, attempts, failure history, owned bundle, authorization
references and receipt history. It uses a locked append-only hash chain and requests
file and directory fsync before effects. This is integrity/recovery machinery, not
cryptographic authentication, independent execution attestation, an OS sandbox, or
power-loss qualification of an arbitrary filesystem.

## Interruption, retry, cancellation and recovery

A session lock prevents two writers to the same session. A torn or modified journal
is preserved and rejected, never auto-truncated. The engine's own journal and
exact owned bytes are reconciled before resuming; prior constraints remain intact.

A finished plan can be adopted after interruption only when its source, full
artifacts, prepared response digest, engine and final planning journal agree.
Interrupted incomplete read-only preparation requires `--retry`, the same reviewed
proposal, a fresh externally anchored prepare scope and an available attempt.
Its partial private directory remains untouched; the next attempt gets a distinct
owned path. This is bounded retry of the same reviewed preparation, not a new
semantic replan or permission to discard a failed attempt.

A completed apply followed by a process crash is adopted without reapplying it.
Partial application never becomes verified. Baseline/modified receipt recovery
requires an explicitly supplied external receipt anchor and a matching completed
engine journal. Both passed and failed completed schedules are retained; recovered
failure remains failure, and a retry still requires `--retry` and scope. Interrupted
execution without independently retained completion evidence stays blocked rather
than replaying effects.

```sh
# Stop exposure/progression; cancellation does not undo an already attempted effect.
python -m jev_integration_evaluator.repository_run /absolute/target \
  --session /caller/private/run --cancel

# Recovery requires the exact owned rollback digest and separate rollback scope.
python -m jev_integration_evaluator.repository_run /absolute/target \
  --session /caller/private/run --recover --scope /caller/rollback-scope.json
```

Cancellation preserves ownership, history and receipts and blocks normal resume.
Explicit owned rollback remains available. The existing engine refuses changed
owned bytes or modes, preserves unrelated concurrent edits, and never restores
unowned paths. A rolled-back bundle stays historical; reapplication needs a fresh
source review and run. A session lock is not cross-bundle repository coordination;
composite transactions and cross-worktree ownership remain issue #13.

## Bounds and coverage

Default bounds are two attempts per operation, 128 journal events, 64 scheduled
input cases and a 60-second per-case/per-command verification deadline. Strict
ceilings are three attempts, 128 events, 64 input cases and 120 seconds. Baseline
executes one mode per case; modified verification executes off, shadow and fixture
active modes. These are finite schedule bounds, not a CPU, memory or deployment-
wide spending guarantee. The journal is capped at 64 MB and each record at 1 MB;
individual archived execution receipts are capped at 64 MB, at most six receipts.
No model/provider spend is enabled by these limits.

Snapshots cover the existing bounded source/configuration policy, not every
repository byte, arbitrary asset, external dependency or installed environment.
Source-byte, mode, added-source and removed-source drift invalidate the decision.
Unsupported language/parser paths remain explicit. Complete arbitrary-repository
snapshotting and native environment contracts still require the remaining roadmap.

The scan includes the extensions `.py`, `.pyi`, `.js`, `.jsx`, `.mjs`, `.cjs`,
`.ts`, `.tsx`, `.go`, `.rs`, `.java`, `.cs`, `.c`, `.h`, `.cpp`, `.hpp`, `.rb`,
`.lua`, `.luau`, `.kt`, `.swift`, `.php`, `.sh`, `.ps1`, and `.sql`; recognized
configuration names (`pyproject.toml`, `setup.py`, `setup.cfg`,
`requirements.txt`, `package.json`, `package-lock.json`, `yarn.lock`,
`pnpm-lock.yaml`, `tsconfig.json`, `pytest.ini`, `tox.ini`, `conftest.py`,
`Dockerfile`, `docker-compose.yml`, `compose.yaml`, `Cargo.toml`, `go.mod`,
`AGENTS.md`, `README.md`, `SETUP_PROMPT.md`); and `.github/workflows/*`.
The bounded report records each included file's bytes hash and mode. The
session re-enumerates the same policy before stages and rejects included-file
additions, removals, byte changes and mode changes. The report's policy and
coverage limitations are part of the decision context.

Ignored directories include `.git`, `.hg`, `.svn`, `node_modules`, virtual
environments, caches, build outputs, `vendor`, `target`, and `.next`;
sensitive-name matches and caller policy excludes are also omitted. Other file
extensions, external dependencies, interpreter installation and generated
runtime state are outside this snapshot. Exclusion means **unknown dependency
state**, not proof that the selected host behavior ignores it. A nondependent
excluded text file is tested not to create a false drift stop; if a selected
host actually reads excluded data, this session alone cannot certify its
stability. Such a dependency needs a separately reviewed and observed bound
before claiming an environment-equivalent result.

Execution is **trusted-host synthetic verification** only. Requesting an isolated
backend fails with `independent_isolation_backend_unsupported`, without silently
executing on the host. The current core probe injects its fixture runtime; this
does not prove actual application bootstrap or provider connectivity. No existing
Python recipe is generalized, and no methods, async seams, package rewriting,
JS/TS runtime, distributed budget, production activation or benefit is advertised.

Local session qualification targets Linux/Python 3.13. Other interpreters,
filesystems, Windows/macOS and hosted jobs must be qualified separately. The
session filesystem implementation explicitly rejects non-POSIX execution.

## Qualification commands

```sh
python -m pytest -q tests/test_repository_run.py tests/test_repository_run_wheel.py
python scripts/run_repository_session_demo.py --out /fresh/private/session-demo
python -m pytest -q
python scripts/validate_package.py
python scripts/run_v11_demo.py --out /fresh/private/v11
python scripts/run_v12_demo.py --out /fresh/private/v12
python scripts/run_implementation_demo.py --out /fresh/private/implementation
python scripts/rebuild_checksums.py --write
python scripts/validate_package.py --check-manifest
```

The session demo uses all thirteen existing generated A–M fixtures, validates real
edited entrypoints through the existing verifier and rolls every target back. It
is not the independent host corpus requested in #9. Installed-wheel tests import
the package outside its source checkout and exercise planning, baseline, apply,
verification, untrusted status and owned rollback. The integrated release checks
are recorded in `validation/REPOSITORY-SESSION-VALIDATION-1.3.0.dev11.md`.
Independent security and real-host qualification remain separate issue gates.

## Integration boundary

The dev10 repository-placement context/outcome and experimental selection flow
remain separate from this fixed-input session. The path-only discovery result is
not a substitute for a complete, policy-scoped source-reviewed negative judgment.
The historical checkpoint's qualification tree was incomplete; its totals are
not release evidence. The current release report records checks against the full
checkout and names the remaining issue #4 work.
