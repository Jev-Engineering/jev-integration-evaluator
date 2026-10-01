# Installed Node connected owner (v1)

This interface extends the default-off Node installation. It supports pinned Linux
Node `v24.18.0`, `jev-1.13.0`, and TypeSafe `/v1/systemone` Choice, Score, and
Noul responses. It does not activate an installed off generation on its own.
The descriptor declares exact `node:sqlite.DatabaseSync`, `AbortSignal`,
`node:https`, and `node:crypto` support requirements; other Node/platform
profiles are refused.

The evaluator CLI accepts a private `node-connected-request-v1` JSON file with
the exact install plan and externally retained install receipt digest. The file
specifies `shadow`, `canary`, or `active`; the approved HTTPS endpoint; the
`env:TYPESAFE_API_KEY` reference; a digest of the host environment; finite
call and cost limits; a private ledger path; and an egress grant. The source
configuration must still say `off`. The new mode is an explicit, separately
approved launch setting, bound to the installed generation and checked by the
host. No key value belongs in the request, descriptor, receipt, or audit.

1. Run `template node-connected-core --request REQUEST --out CORE` to obtain
   the exact source, runtime, toolchain, configuration, and budget scope digest.
2. Have the independent host authority issue a finite egress grant for that
   core. Put the grant in a new request file. Its digest is an anchor, not proof
   that it was issued by the host.
3. Run `template node-connected-plan --request REQUEST --out DESCRIPTOR`. Store
   the private descriptor and its displayed SHA256 separately. For canary or
   active, provide private raw gate references and hashes; the planner reruns
   `evaluate_study` on those exact inputs and requires observed keep evidence.
   The host independently authenticates the recomputation, deployment grant,
   and activation receipt. Synthetic studies cannot activate these modes.
   A new plan is also refused when the egress grant, deployment grant, or
   activation receipt is outside its `issued_at`/`expires_at` window; the
   later status recheck compares the binding only and leaves time to the host.
4. `template node-connected-status --request REQUEST --descriptor DESCRIPTOR
   --trusted-descriptor-sha256 SHA256` rechecks source and evidence without
   running the host.
5. Configure the host's independent `verifyAuthority`,
   `currentEnvironmentDigest`, and audit callbacks. Create a private owned
   session with `template node-connected-session-create --session SESSION
   --request REQUEST --descriptor DESCRIPTOR --observation OBSERVATION
   --launch-environment LAUNCH_ENVIRONMENT --trusted-descriptor-sha256 SHA256`.
   The private observation file declares exact, separately owned ready,
   entrypoint, and integration paths with prelaunch and expected hashes. The
   launch environment JSON binds those paths to `NODE_READY_PATH`,
   `NODE_EFFECT_PATH`, and `NODE_INTEGRATION_PATH`. Creation rechecks the
   installed receipt and absent baseline files; launch repeats that check.
   Retain the returned session head outside the session. Set `JEV_RUNTIME_MODE`
   to the exact approved mode and provide the credential through its environment
   reference. Create a finite `template-delivery-scope-v1` with the session run
   ID, descriptor digest, retained head and launch grant. Call
   `template node-connected-session-launch --session SESSION --scope SCOPE
   --approve-scope-sha256 SHA256`. The supervisor records launch intent and
   process identity before releasing the child. The host's generated adapter
   calls `initializeConnected` before its seam.
6. Use `node-connected-session-observe` with the retained head. After an
   interrupted action, use `node-connected-session-resume` with that head to
   reconcile the same process; an uncertain launch is never replayed. Use an
   exact new scope for `node-connected-session-stop` or `-disable`. These
   actions cannot authorize an egress grant or resume a suspended ledger.
   The supervisor confirms exact Node executable handoff and hashes each
   predeclared observation path after launch. Each observe call journals the
   actual hashes or absence plus the roles whose bytes match the schedule;
   changed files become false on the next observation. The
   session status also reports process liveness. Raw fixture effects do not
   establish provider benefit or canary qualification.

`ConnectedNativeOwner` checks installed file bytes and independently authenticated
grants at startup, invocation, egress, and effect. Source drift, credential
rotation, expiration, revocation, or a failing monitor callback suspends the
ledger; there is no automatic resume. The durable SQLite ledger records charges,
tasks, invocation identities, and unresolved provider reservations. It prevents
effect replay after a crash or an ambiguous provider timeout. A second process
cannot share its exclusive ledger. This is a single-owner limit, not a claim of
distributed budgeting. The CLI reports only status and anchored digests; it
never prints command output, provider bodies, or credential values.

In shadow, the host executes its authorized baseline while the provider
assessment runs separately. A grant revoked after that baseline cannot undo
its effect. The host can call the generated adapter's `status()` monitoring
hook; this rechecks authority and durably suspends the owner. The offline
installed fault fixture proves one baseline effect, suspension, and refusal of
a later session after a grant is restored. It does not qualify active effects.

The offline fixture uses a fake transport **only in shadow** and is labeled
`synthetic_protocol`. It verifies typed parsing, grant refusal, source drift,
ledger replay, hardlink refusal, and installed supervised execution. The
dedicated `connected-node24-qualification` CI job pins Linux CPython 3.13.5,
Node 24.18.0, npm 11.16.0, and trusted TypeScript 5.8.3; it requires all 26
installed tests and 19 native tests with zero skips. This job is a configured
gate until its exact revision has actually run. It is not a JEV live measurement.

The [installed fault matrix](../tests/test_node_template_connected_faults.py)
runs once each for installed CommonJS, ESM and TypeScript hosts through the
installed evaluator CLI and the normal Node command, in shadow with the fake
transport. It reads every outcome back from the host's append-only effect
file, the host audit sink, the fake transport's request log, the durable
ledger and the session journal. Per format it exercises:

- reviewed configuration changed after install (a promoted `mode`, and a
  byte-only change): `node-connected-session-launch` is refused before a
  launch is journaled, a child exists or a ledger is created; restoring the
  exact bytes lets the same unchanged scope launch once;
- a settled invocation identity replayed by a second process: refused with
  `effect_replay_denied`, no provider request, no effect, ledger unchanged;
- an egress grant revoked between two seam calls of one process: the first
  baseline effect stays, the second call is refused with no provider request
  and no effect, the ledger is suspended, and a later session started after
  the grant is restored performs nothing;
- a provider response held past the reviewed `timeout_ms` and then delivered,
  truncated duplicate-key bytes, a well-formed answer whose probabilities do
  not sum to one, and an asynchronously rejected transport call: each leaves
  exactly one baseline effect and a `shadow_failed` audit record, and never a
  `shadow_result`;
- the host executor rejecting asynchronously after its effect: the normal
  command fails, the effect is not retried, the invocation stays unsettled,
  and a later process with the same invocation identity performs nothing;
- `node-connected-session-stop` while the fake transport still holds its
  response: the stop is journaled, no response is adopted, and the effect file
  still holds one effect.

Ledger accounting in these cases is conservative. Each provider request is
charged its reviewed `cost_upper_bound` when it is reserved. A reservation is
resolved only when a valid typed answer arrives inside the timeout; a late,
malformed, mistyped, rejected or abandoned response keeps both the charge and
the unresolved reservation. A later owner on a ledger with an unresolved
provider reservation, an unsettled effect or a suspension is refused at
startup, before the host's baseline runs; the operator must review that
ledger and bind a new one. There is no automatic resolution.

Limits of this matrix: the fake transport is refused outside shadow, so no
installed case reaches a selected (treatment) effect or the active fallback
path; those stay covered only by `tests/native_js_runtime.test.cjs`. The
generated seam passes no `AbortSignal`, so installed cancellation is the
supervisor's stop of the owned process, and `AbortSignal` cancellation stays a
native unit test. The supervisor forwards a fixed list of fixture environment
names to the child (`JEV_FAKE_TRANSPORT_*`, `JEV_TRUSTED_GRANT_FILE`,
`JEV_INVOCATION_ID`, `JEV_FIXTURE_FAULT`); only the fixture entrypoint reads
them and they carry no authority. Cross-process budget contention is not
exercised because the ledger has one exclusive owner. An interrupted build or
install is classified (`*_interrupted_review_required`) and is never recovered
by status or by a retry. Its owned partial root can be removed only by the
separately planned and approved `node-package-recover` or
`node-install-recover` of the
[install adapter](template-node-installation-v1.md), which retains the
interrupted attempt in a recovery journal and leaves other generations
untouched. That recovery is off-mode installation evidence only; it has not
been exercised under a connected session, and power-loss durability is not
covered.
The always-on `tests/test_node_template_connected_gates.py` drives the planner
with in-test fixture rows over a byte fixture of an installed generation (the
pinned install check is replaced there). It covers refusal of synthetic
studies, failing or insufficient raw holdouts, success-shaped summaries,
omitted or promoted missing outcomes, wrong-mode, differently bound, or
out-of-window grants and receipts, and configuration or source drift after
install; shadow reads no gate evidence. The native tests cover a provider
timeout: one baseline effect, no selected effect, a retained reservation, and
a discarded late result. None of these fixtures is observed evidence. Real
provider qualification, externally authenticated grants, observed canary and
active gate receipts, and production host monitoring remain pending. The
legacy `NativeRouter` and its receipt format remain supported.
