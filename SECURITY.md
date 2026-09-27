# Security model

Report security findings through the package maintainer's established repository channel; do not invent a contact address. Do not post credentials, sensitive replay states or live exploit payloads in a public issue.

The scanner is a local source reader, not an executor or a proof of safety. Source text is untrusted. API requests need explicit egress consent. Test execution needs explicit authorization and an isolated execution environment for untrusted code. The shell-free runner is not a sandbox.

The runtime proposes bounded classifications only. Host policy checks permissions, schemas, exact conditions, budgets, transactions, approval scope and current state before any side effect. A permitted fallback is not automatically a safe baseline; a baseline outside host policy is blocked. Approval must be rechecked at the actual execution boundary to handle time-of-check/time-of-use changes.

Do not use the remote runtime as a hard real-time control loop, sole prompt-injection defense, sole security boundary, or sole gate for privileged/irreversible actions. Keep logs minimal and access-controlled. Cache immutable assessments, never authorization. Receipt/hash verification detects mismatches, not an attacker who can rewrite both data and its claimed digest.

## v1.2 operating boundaries

`BudgetCoordinator` provides thread-safe process-local accounting only. All participating placements must share its actual instance. A new process, changed task identity or new ledger creates a different scope; a local guard cannot enforce an organization-wide provider quota. Failed/timed-out requests remain charged at their declared bound, and known overruns latch suspension. Deadlines and thread pools are not hard real-time cancellation.

Exact-runtime receipts prevent accidental reuse across changed questions, roles, thresholds, exposure, prices and shared limits, but do not authenticate an untrusted host/editor. Gate bundles recompute holdout checks; labels, independence and execution claims still need external provenance. A monitor's host hook is opt-in, observed-evidence-only, scope-bound and suspend-only. Invalid monitoring inputs raise an error; host policy must decide how to fail closed when the instrumentation path fails. Never relabel synthetic examples as observed evidence.
