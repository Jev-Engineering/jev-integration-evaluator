# Installed connected shadow delivery v1

This is an opt-in Linux x86-64 CPython 3.13 path for one independently reviewed
Alpha 1.0.2 console host. Package and install retain the existing **off** mode
and receipt semantics. A connected launch starts only from a separate
`connected-delivery-plan-v1` and exact, expiring session scope. It does not
interpret a package receipt, installed binding digest, or mode flag as egress
authority.

The source application, modified verification, offline wheel build, and
installation follow [the package profile](template-installation-v1.md). The
read-only `template connected-installed-bind` step then recomputes wheel RECORD,
installed module origins and bytes, and the retained reviewed project file from
externally anchored package and install receipts. The output digest must be
retained independently. The Alpha 1.0.2 fixture includes a code-owned
`connected_authority.py` options loader in the reviewed source and wheel map;
the original Alpha versions remain separate fixtures.

The host owner provisions two owner-private files **outside** the package and
installed environment: an options reference and an issuer **public** key.
The reference describes the exact installed binding, pinned HTTPS endpoint,
`jev-1.13.0` model, environment and source digests, budgets, egress grant,
ledger path, and detached P-256/SHA-256 signatures. The public key path and
its independently retained SHA-256 are sealed into the supervisor's exact plan
and child launch environment. The private issuer key never enters the child,
wheel, source or committed fixture. The loader checks owner/mode/link count,
verifies signatures with fixed `/usr/bin/openssl` argv and a clean OpenSSL 3
environment, and recomputes the verifier's binary hash/version and runtime
facts before each route. A changed public key or verifier needs a new reviewed
plan and issuer signature. Secret values and raw prompts do not belong in
plans, scopes or reports.

The actual `TYPESAFE_API_KEY` is available to the child only after deliberate
launch; plan/configure/status need no credential. A local synthetic issuer and
loopback endpoint in tests exercise startup without a real provider request.

`template connected-plan` binds the installed report, private reference paths,
independent external observation schedule and **shadow** mode. It rejects
canary and active requests because this checkpoint has no observed canary or
active gate receipts. `template connected-configure` creates an owner-private
session after exact plan-digest approval. `template connected-launch` requires
an exact current session head, public-key hash, action and expiry in a separate scope plus the
credential at launch. The supervisor writes a durable launch intent, records
the child process identity before releasing its inherited pipe, and never
replays an attempted or uncertain console effect. `template connected-resume`
reconciles pending intent without replay; `template connected-status` reads
the journal and independent file outcomes; `template connected-stop` targets
only the recorded Linux process identity through pidfd signaling.

An installed protocol test checks source binding, normal console startup, public-key
checks, durable ledger creation, duplicate-launch refusal and exact stopped
state with the host's hard gate closed. With a separately permitted fixture,
it checks an intended shadow decision, independently recorded baseline effect,
one local TLS TypeSafe response, and a wrong-model fault with fallback across
two sessions using one ledger. These are offline synthetic checks against a
loopback server. They establish no live provider reachability, observed benefit,
or canary/active eligibility. Real egress requires separately provisioned
host credentials, endpoint approval, budget and spend limits, and external
grant signatures. Canary/active additionally require raw observed holdouts and
exact runtime receipts validated by `HostRuntimeLifecycle`.
