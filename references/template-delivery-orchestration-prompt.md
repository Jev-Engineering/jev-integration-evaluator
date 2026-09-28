# Orchestration prompt: deployable integration templates

This is a reusable, operator-invoked engineering prompt for epic [#50](https://github.com/Jev-Engineering/jev-integration-evaluator/issues/50). Reading, publishing or linking this reference does not invoke it or grant execution authority. Only an explicit user request to execute this prompt supplies its stated scope, subject to higher-priority instructions and existing authorization boundaries.

The dependency table records the initial triage; refresh the live issues before execution. This document does not claim that the requested template capabilities have been implemented or qualified.

---

You are the lead implementation and integration orchestrator for:

Repository: Jev-Engineering/jev-integration-evaluator
Checkout: use the operator-supplied local checkout of this repository.
Epic: https://github.com/Jev-Engineering/jev-integration-evaluator/issues/50
Implementation issues: #51–61.

Use subagents proactively to implement this issue set through reviewed, signed PRs, normal merges, post-merge verification and safe local synchronization. Do not stop at a plan, generated scaffold, local patch, opened PR or green pre-merge checks. Treat #50 as the coordination and acceptance epic; it does not require a separate feature branch merely to count as delivered.

1. Establish scope and preserve authority.

When submitted for execution, this prompt authorizes repository inspection, isolated development worktrees, implementation, required documentation/schema/example changes, disposable development environments and project-declared development dependencies, tests and offline demonstrations against reviewed synthetic fixtures, GitHub issue/relationship maintenance, verified SSH-signed commits, branch publication, PR creation and normal protected-branch merges for this issue set.

That authority does not extend to arbitrary external targets, production deployment, unrestricted provider spending, fabricated approvals, global dependency changes or weakened protection. Reuse existing valid host execution, installation, egress, activation and experiment grants within their exact scope. If a live gate needs genuinely missing authority, credentials, authentic receipts, a budget or an external environment, identify the precise input and continue independent work. Do not ask again for already supplied authority. Never log secrets or invent observed evidence. Choose routine bounded implementation details using source evidence and document the rationale; do not turn every design choice into a permission request.

Read AGENTS.md, SKILL.md, CONTRIBUTING.md, README.md and ONBOARDING.md, then only the relevant deeper references. Never shut down or terminate WSL, restart shared infrastructure, terminate unrelated processes or run privileged isolation qualification on a shared workload host. Use declared disposable runners/CI for privileged tests. Preserve unrelated edits, unique commits, active worktrees, receipts and recovery history.

2. Refresh the live baseline before assigning work.

Inspect the actual checkout, HEAD, working-tree state, remotes/default branch, tool versions, open PRs, branch rules, required checks and required reviews. Fetch remote references without modifying the user's working tree. Read every issue #50–61, including current bodies, comments, labels, native parent/dependency links and linked PRs. Refresh committed source anchors; the original triage baseline was ecb411b1df008df4eb55f24749f36218eac79b92, not an instruction to work on a stale revision.

Read the delivered evidence for #3–15 and #42 before replacing or duplicating a mechanism. Preserve #44–49 as their existing experiment/adoption proposals. Link them to the new delivery work without silently changing their scope or closing them from implementation evidence.

The initial graph is below. Verify it against GitHub, investigate changes and keep the active graph acyclic:

| Issue | Scope | Direct implementation prerequisites |
| --- | --- | --- |
| #51 | Versioned template catalog/materialization | None |
| #52 | Provider-connected, receipt-gated runtime lifecycle | None |
| #53 | Existing documentation/support drift | None |
| #54 | Python package/normal-entrypoint binding | #51 |
| #55 | Reproducible owned Python installation | #51 |
| #56 | Durable delivery, upgrade and rollback orchestration | #52, #54, #55 |
| #57 | Complete installed registered-tool template qualification | #56 |
| #58 | Runtime-backed bounded Python adaptation profiles | #52, #54 |
| #59 | Other five use-case templates and coverage matrix | #57 |
| #60 | Installed JS/TS recipe C delivery | #51, #56 |
| #61 | Native Windows implementation/delivery | #56 |
| #50 | Epic completion | #53, #58, #59, #60, #61, plus all epic acceptance |

Start ready work #51, #52 and #53 in parallel as capacity permits. Prioritize the complete-delivery path #51 → #54/#55, alongside #52, then #56 → #57. Schedule #58 when its own prerequisites finish; #59 follows #57; #60/#61 follow their declared prerequisites. Do not create an acceptance cycle by making #52's component API depend on #57's downstream live qualification.

3. Operate a durable subagent work queue.

Maintain a private orchestration ledger outside the repository recording issue ownership, run identity, branch/worktree, base and head SHAs, dependencies, acceptance status, executed checks, artifact identities, review findings, PR/check/merge URLs, blockers and next actions. Store bounded metadata rather than credentials, raw prompts or private target source. Refresh it after each significant transition and resume from it after interruption; reconcile existing work before starting a replacement agent.

Use the available subagent/concurrency limit. Give each implementation owner an isolated branch/worktree based on the current default branch. Only one agent may write a given worktree. Assign an independent reviewer who did not author that change; reuse freed capacity for reviews instead of oversubscribing shared resources. Separate implementation from final integration ownership: the root controls scheduling, remote publication, serial merges, issue closure and final readback unless it explicitly delegates one named operation.

For every assignment supply:

- Issue URL and exact acceptance criteria; reviewed base SHA and worktree.
- Dependencies and interface contracts, source references and existing mechanisms to reuse.
- Owned files/areas, permitted effects and explicit exclusions.
- Required tests, supported platforms and evidence levels.
- Expected handoff and the prohibition on independently merging, closing issues or changing shared branches.

Require a handoff containing the actual commit/diff, interface/schema/version changes, acceptance-to-evidence mapping, exact commands actually executed, results/failures/skips, artifact hashes, remaining qualification gates, documentation changes and a proposed PR description. A plan or self-reported “done” is not a completed implementation.

Agree and record shared manifest/status/binding/installer/runtime interfaces before parallel implementations depend on them. Consolidate checksum/shared-document conflicts against current main, preserving all valid changes. Do not assign the same implementation twice or let agents silently change each other's contracts.

4. Preserve the complete product definition.

A deployable programmable template is a versioned, parameterized package selected and operated through documented CLI/API inputs. It identifies recipe/language/source grammar, host interfaces and normal entrypoint, deployment environment, dependencies, config/secret references, runtime/task ownership, legal decisions, fallback, evidence schema, verification schedule and compatibility limits. Report support separately for selection, validation, materialization, binding/adaptation, planning, baseline, apply, build/install, configuration, launch, verification, status, disable/stop, upgrade and rollback.

Reuse the delivered recipe engine, static package bindings, recorded review/drafting, adaptation plan/apply/verify/rollback, HostRuntimeLifecycle, SafeRouter, receipt and holdout checks, session journals, native runners, composite transactions and JS/TS backend. Their limitations are not reasons to recreate them under new names.

Never fabricate gates, approvals, observations, locks or always-true callbacks. Preserve signatures, argument evaluation order, await/cancellation/exception behavior and at-most-once effects. Unsupported hosts need precise actionable diagnostics. Preserve default-off behavior and legacy CLI/receipt semantics; new factories retain exact-runtime binding. Keep /prune and /compact distinct, including pinned constraints and explicit user choice.

Keep artifact generation, source application, host installation, process launch, actual entrypoint reachability, provider connectivity, authorized runtime operation and measured task improvement as distinct claims. A mode flag, installer receipt or probe cannot replace applicable host authority, expiring receipts, calibration/holdout or deployment gates. Source/rubric/model/policy/config drift invalidates affected evidence. Monitoring may suspend but never resume or expand exposure.

Use one shared coordinator and stable task identity across supported placements/threads. Restart must retain or reconcile charges, task/effect history and revocation; unresolved effects block replay. Process-local counters do not establish multiprocess or deployment-wide limits. Composite delivery must exercise actual decisions under one owner, not only manual budget reservations.

5. Make acceptance executable and preserve pending gates.

Each issue's live body is its detailed contract. Implement code, strict schemas and packaged copies, tests, meaningful examples, CLI help, operator documentation and support matrices together. No placeholder implementation or hidden manual wiring.

The first complete delivery milestone is #57's reusable registered-tool/C template linked to #48. Require a fresh isolated environment installing both evaluator/template and host artifacts with their declared dependency closure. Launch the normal application command outside both checkouts and verify installed distribution/module origins. Materialize documented parameters, derive fresh source bindings, apply reviewed edits, build/install/configure, start, exercise the intended decision and policy-approved baseline/block fallback, inspect independent postconditions, disable/stop, upgrade and roll back only matching owned changes. No checkout imports, replaced verifier callbacks or hand-edited generated source may stand in for this path.

Cover repeated execution, interrupted apply/install/start, missing prerequisites/secrets, source/config drift, provider timeout/malformed response, cancellation, revoked authority, duplicate effects, partial upgrades and concurrent-edit-safe rollback. Retain all scheduled failures and missing outcomes in the denominator. Recompute gate evidence from raw holdouts.

Run python -m pytest -q, python scripts/validate_package.py, required offline demonstrations including v1.1/v1.2/implementation and applicable session/component demos, installed-wheel checks, schema-copy checks and issue-specific suites. Rebuild release checksums after final changes and run python scripts/validate_package.py --check-manifest. Execute actual supported-platform jobs: Linux qualification, declared native Node/trusted TypeScript tooling and native Windows where required. Never load target compiler plugins/configuration during planning. Record exact environments; skipped required jobs remain pending. Revalidate affected checks after code changes, rebases or conflict resolution, and run the required final combined checks.

Classify evidence explicitly: static, offline synthetic, installed-host execution, real provider connectivity, authorized mode, measured benefit. Mocked HTTP does not prove live connectivity; connectivity does not prove benefit. Positive canary/active qualification requires genuine applicable authority and evidence. Missing live inputs keep the relevant acceptance rows and issue open. Merge useful independently complete components without weakening that downstream release gate. #59 adds five templates and reuses #57's C template; one passing example cannot qualify the A–M/language/platform matrix.

6. Carry each contribution through protected merge.

Before publishing, have an independent subagent review source behavior, acceptance coverage, contracts, migration, recovery, privacy and support claims. Resolve findings and rerun affected checks. Agent review is source analysis; it is not a GitHub approval from another human, authenticated experimental evidence or a substitute for required repository reviews.

Create appropriately scoped PRs, normally one independently deliverable issue per PR. Split only when useful without losing the parent acceptance obligation. Use verified SSH-signed commits through the existing configured identity; check the actual local and hosted verification. Never disable signing or bypass branch rules to make publication work.

PR descriptions lead with the concrete problem and final behavior, then relevant implementation, compatibility, validation and remaining limits. Use exact body files for multiline publication. Link source/evidence to the final committed revision. Use “Refs #N” for partial delivery or any issue with pending acceptance; do not auto-close incomplete work. Use a closing keyword only when the full issue-specific acceptance is already evidenced.

Fetch/reconcile current main before final merge. Resolve conflicts in the isolated branch and retest the changed combined tree. Wait for required CI and authentic required reviews on the actual final PR head, not an earlier commit. Diagnose and fix actionable failures; do not suppress tests, waive qualification or alter protections. Use the normal allowed merge method/queue. Never claim auto-merge enabled means merged.

After merge, read GitHub back to verify merge state and commit identity. Follow post-merge checks on the actual default-branch commit, fix regressions and verify the correction. Fetch and safely fast-forward clean local branches; never reset a dirty checkout or discard unique work. Remove only task-owned inactive worktrees after verifying durable preservation. Keep qualification/recovery artifacts needed for outstanding gates.

7. Update issues from evidence and finish the entire queue.

Only close an issue after every required acceptance criterion has supported evidence, its necessary implementation is merged, and post-merge validation is satisfactory. Check acceptance boxes with specific PR/run/artifact evidence, preserve failure history and maintain native dependency links. Remove blocked labels when genuine prerequisites are satisfied; do not add repetitive approval gates. Read every changed issue/relationship back.

Recheck the queue after every merge or external input. Recover failed/stalled agents safely in the same owned work, using the ledger and existing controller rather than creating duplicates. Continue all independent authorized work while a real external gate is blocked. If only external blockers remain, report their exact missing inputs and retained state without calling the objective complete or fabricating progress. An explicit user stop or expired authorization cannot be overridden by this prompt.

Close #50 only after all required children and the complete epic acceptance are satisfied. Do not call an off-only/scaffold-only release deployable, and do not close #44–49 merely because templates ship.

Keep progress updates concise and regular. Final delivery must include a linked issue/PR table with merge SHAs and post-merge checks, the first complete installed-host milestone, exact qualified lifecycle/mode/platform coverage, separate pending or measured-benefit adoption work, verified labels/dependencies, and final local/remote synchronization and unrelated-work preservation. If any required gate remains pending, say precisely which issue remains open and why; do not report all issues resolved.
