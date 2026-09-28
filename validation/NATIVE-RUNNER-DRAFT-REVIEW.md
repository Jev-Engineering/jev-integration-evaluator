# Native runner draft review checkpoint

The supplied `jev-roadmap-checkpoint-20260927.zip` proposes an additive Linux
chroot/seccomp Python runner. This branch stages its 12 source, schema, script,
test and reference files for review only. It does not connect the backend to
`repository-run`, existing implementation receipts, independently observed host
postconditions or provider bootstrap. Issue #8 remains blocked by incomplete
issue #4 and requires an independent security review before merge.

The packet reports 102 standalone tests passed in its own privileged Linux
x86-64/CPython 3.13.5 environment. That is supplied evidence, not a reproduction
on this checkout. On this shared WSL host, all **102 runner tests skipped** because
the required privileged launcher is unavailable; no jail or escape claim was
verified here. Static Python compilation and deterministic schema generation
passed. The full WSL Linux/CPython 3.12.3 suite completed with **1,438 passed,
106 skipped**: 102 privileged runner cases, three non-POSIX checks and one
trusted Node/TypeScript case. Package validation passed with 51 mirrored schemas.
A Windows-local
validator invocation failed on the existing console encoding before checking
the package; the WSL invocation passed. The release checksum manifest and hosted
checks are reviewed on the draft head separately.
The v1.1, v1.2, implementation, capability, selection, repository placement,
repository conclusion and repository session offline demonstrations passed on
disposable synthetic fixtures; they do not exercise this standalone runner.

No test here establishes a real TypeSafe/SafeRouter/HostGate/BudgetCoordinator
connection, arbitrary target safety, production activation or measured benefit.
Do not treat generic CI green, including skipped privileged tests, as issue #8
acceptance. The next implementation must connect exact session scopes, independent
host observations and postconditions, then run the privileged isolation matrix
in a disposable authorized environment with external security review.
