# Review gate invariants

Version 1.3.0.dev6 strengthens `apply_reviews` on the dev5 baseline. It protects
the issue #5 eligibility boundary and the mandatory exclusions needed by issue #7.
The repository implementation roadmap remains open.

## Behavior

A semantic review may strengthen an exclusion but cannot remove an existing
`preferred` or `mandatory` deterministic exclusion. A `mandatory` classification
cannot be downgraded to `preferred`. A `NONE` pattern retains its existing
anti-pattern gate. A hard-real-time exclusion cannot be cleared by setting
`hard_real_time` to false, even in an otherwise source-matched review or a review
whose `approved` value is false. High scores cannot override these checks.

Reclassification requires a separate fresh discovery/policy decision; this
change supplies no reclassification command or permission. A reviewer label or
source digest is not an authenticated authorization credential.

All candidate changes are staged before committing the complete review batch
in memory. Any validation error leaves the input inventory unchanged, including
successful-looking earlier reviews in the same batch. Duplicate candidate IDs
are rejected instead of silently choosing the last candidate. Mutable review
payloads are detached, so changing a caller-owned dimension or evidence list
after validation cannot change the stored result.

On success, the input scan dictionary and candidate/list references are retained.
The candidates receive the validated values and are sorted deterministically.
Existing callers that hold a candidate reference can still attach later trace
data to it. Nested review proposals are detached. This is in-memory validation
atomicity, not a durable filesystem transaction, a concurrent-writer protocol,
a session journal, or an isolation backend.

## Focused qualification

`tests/test_review_gate_invariants.py` uses manually authored synthetic
unit-level inventories. It exercises the real scoring, configuration and I/O
modules without stubbing their validators. It does not scan or modify a target,
import a target module, call a provider, or produce observed-benefit evidence.

At the pinned baseline, the supplied tests report 49 failures and 14 passes. After
the correction, all 63 supplied cases pass, plus two integrated regressions for
current caller references and a malformed untouched candidate. These are test
cases, not 49 distinct bugs. Six
mutation checks independently remove the real-time guard, existing deterministic
guard, mandatory-downgrade guard, duplicate-ID guard, batch isolation, and
proposal detachment; each mutant is detected by unchanged tests.

The supplied patch and tests came from an earlier partial checkpoint. The
integration adds a compatibility correction after reproducing a stale candidate
reference in a current test. The tests use source constructed in this repository;
they are not an independent host corpus or application benefit measurement.

## Coverage and remaining work

The dev5 nomination-to-inventory bridge remains available. This change does not
implement the issue #7 selection contract, complete issue #5's reviewed
no-useful-placement outcome, or close any roadmap issue. Runtime defaults,
source identities, estimation requirements, provider authority and activation
policy retain their separate requirements. See the dev6 validation record for
executed local and hosted checks.
