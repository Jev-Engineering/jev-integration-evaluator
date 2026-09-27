# Wire JEV-D83B745FC7BF into the host

Source: `agent.py::dispatch_once` lines 4–9.

The generated adapter is executable, but no host source was rewritten. An authorized agent must inspect this exact source, bind the rubric labels to legal host actions, build the minimal state, call `propose`, and recheck deterministic policy at the execution boundary. Do not treat an assessment as authorization.

Create a worktree when appropriate, run the existing baseline, add this adapter behind an off-by-default flag, and generate a content-hashed patch plan containing the host call-site edit. Review that diff and approve its exact digest before applying it. Add unit/integration/failure-injection fixtures, run the host's tests only with execution approval, and collect shadow evidence. Use `create_router` to require expiring, ordered-question-bound activation receipts. Freeze chosen thresholds and validate an untouched holdout; collect a separately frozen paired study before canary/active adoption. `suspend()` and `revoke_activation()` latch off new and in-flight proposals; host policy must recheck before execution.

Traceability: `JEV-D83B745FC7BF-EXP-01`; questions `c95218a2ec816a604aa5efdbaa4c9a48e28a274bd19289ec194eed3eddb0b44b`.

Fallback: unavailable/timeout/invalid/low-confidence → permitted baseline or inspect; failed host authorization → block/request approval. Never widen permissions to make the integration work.
