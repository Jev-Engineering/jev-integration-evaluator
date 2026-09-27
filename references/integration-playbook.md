# Authorized integration playbook

For development of scripts that generate and verify host call-site edits, see [the executable implementation engineering prompt](executable-implementation-prompt.md). The current commands below provide adapter generation and exact patch application; the prompt describes the missing orchestration and transformations as future work.

## Establish the baseline first

Read the candidate's exact source/hash, callers, consumers, policy and tests. Determine the actual objective, legal choices and available evidence. Reject a placement when exact checks suffice. Record current behavior and observable postconditions before changing code. Running repository tests executes arbitrary code; obtain separate execution scope and use isolation for untrusted projects.

## Prepare isolated changes

Use `worktree --approve-create` only when an explicitly approved new branch/worktree is appropriate. It creates a scoped `jev/...` branch locally; it never pushes, merges or deploys. Preserve concurrent user changes. A generated adapter is a useful implementation artifact, not proof that an arbitrary codebase has already been modified.

`scaffold` writes `adapter.py`, a runnable default-off regression test, an integration manifest and source-specific wiring instructions. It includes exact bounded rubrics, the primary and evidence question IDs, runtime source provenance and the experiment ID. Map classification labels to legal host behavior explicitly; for a relevance classifier, for example, labels are evidence classes, not arbitrary executable tools.

Construct the minimal state with stable IDs, relevant source/evidence, current legal candidates and objective constraints. Keep trusted instructions outside untrusted state; all quoted source remains data. Do not silently truncate evidence or hide contradictory facts. The live client's conservative request-byte ceiling is an application limit, not a tokenizer or a claim about the provider's exact token budget.

## Wire policy without weakening it

Capture the baseline proposal. Preserve deterministic hard blocks, approvals, exact parameter/schema checks, candidate registry, state revision and transactional rules. Call the adapter behind a default-off flag. The router returns an action **proposal**, never executes it. The host rechecks legal membership, approval and current state immediately before execution. Never give JEV unrestricted tools, SQL or shell strings to execute.

Off returns the permitted baseline without a model call. Shadow uses a bounded nonblocking worker queue and returns baseline immediately; saturation drops shadow work. Active/canary require a source-independent but exact model/rubric/policy/threshold activation receipt with real held-out evidence. Canary selection is stable for an entire task, not independently reassigned at each decision. Host authority and task state still govern the final action.

Provide a stable task ID; do not reset it per retry to evade budgets. Call `release_task` only when the whole task ends. Remote calls require a conservative declared spend upper bound; reservations persist for failures/timeouts. Known actual cost above the reservation updates the budget and blocks further spending where necessary. Prices default unknown. A transport timeout does not guarantee a hard wall-clock deadline, and custom clients must honor their timeout contract.

Unavailable, invalid, late, unconfident or abstaining assessments return the permitted baseline or an explicitly legal inspection/approval path. An illegal baseline blocks. Repeated failures open a circuit. Audit failure also falls back. Cache only explicitly immutable state within a tenant/task-version scope; state, evidence/questions, model, policy and allowed actions enter the key. Never cache approval. Recheck state and permissions after cache retrieval.

## Review and apply the exact diff

Create `changes.json` as a list of `{file: relative_path, new_content: full_text}` entries. `patch-plan` captures old/new content hashes, unified diffs, repository-path identity, opportunity IDs and a canonical plan digest without changing the target. Inspect the entire diff, obtain approval for that exact digest, then use `apply --approve`.

Apply preflights all target hashes, rejects protected paths/symlinks/traversal and rechecks each target immediately before writing. It preserves existing mode bits and attempts rollback of its own completed writes on error without overwriting concurrently changed data. A dedicated worktree remains the preferred protection against concurrent writes. The digest prevents accidental plan mismatch; it is not an authentication service. Apply does not install, execute tests, push, merge or deploy.

## Verify, record and roll out

Run existing and new tests only with authorized commands. Add unit cases for all answer labels, missing/contradictory evidence, API failures, invalid distributions, low confidence, illegal actions, approvals, TTL/scope changes, budgets, circuit opening, shutdown, queue saturation and off-mode equivalence. Add integration tests that verify postconditions rather than only exit code/HTTP status.

The generated adapter attaches source location, candidate ID and experiment ID to metadata-only runtime logs. Logs include request/question/model/policy hashes, proposed decision, probability, provider confidence, usage, elapsed latency and known/unknown cost. They do not log raw state by default. An explicitly approved replay dataset stores the necessary decision state separately under access controls and retention rules.

Use `link` to attach the actual integration manifest, test receipt or outcome receipt to the inventory. Each receipt must match opportunity, source hash and experiment ID. The record stores the artifact filename and SHA-256. Linking evidence never grants deployment authority or silently upgrades a tier.

Collect shadow resources/disagreements and independent labels; obtain actual paired task outcomes before claiming rescues. Freeze a calibrated policy, evaluate ablations, review useful-effect and safety/resource evidence, and authorize only a bounded canary. Roll back through the host feature flag when declared limits are exceeded. Document keep/modify/disable/needs_more_evidence, diff summary, completed/failed/not-run tests, fallback operation and residual risks.
