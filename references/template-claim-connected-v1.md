# Installed claim support connected shadow

Timeout diagnostics use `EvaluationTimeoutError`, a subtype of the existing
`InputError`. Direct transport timeouts, wrapped timeout causes and responses
over the elapsed budget receive this type; other transport failures retain
the generic error. The host audit writes only the fixed type and error-class
metadata when the actual router reports this timeout. Provider exception text
is suppressed. The installed timeout schedule below exercises this correction.

The finite `claim-m-v1` profile binds `claim_host/host_claim_support.py`,
`claim_host/console.py` and `claim_host/connected_authority.py` to exact source,
wheel RECORD and installed origins. It uses recipe `python.M@1.0` and the
existing code-owned claim consumer, exact citation spans and critical-claim
policy. A typed answer supplies an observational disposition in shadow;
release still requires host approval, exact source/span validation and durable
raw support/audit readback. The normal baseline remains `inspect`.

## Parameters and operator sequence

Run materialize, source bind, independently reviewed apply/verify, package and
install using the [existing claim template](claim-template-offline-v1.md).
Derive a fresh installed binding from the exact package/install receipts. Do
not edit generated adapters or installed files. Package/install remain off.

Select `--host-profile claim-m-v1` with `template connected-plan` and pass the
exact installed binding and external outcome schedule. Required owner-private
references are `M_CONNECTED_REF` (signed exact installed binding/egress
manifest) and `M_AUTH_PUBKEY_FILE` (public-only P-256 key). The supervisor
injects their SHA-256 anchors; callers cannot supply the injected names.
`SSL_CERT_FILE` is an optional independently pinned trust certificate.

The reviewed host uses `M_EFFECT_DIRECTORY` with existing owner-private
`claim-one` and `claim-two` subdirectories, `M_READY_PATH` and
`M_RELEASE_PATH`. `M_TASKS` is `two` or `duplicate`; duplicate scheduling must
be refused before replay. `M_HOLD` and `M_APPROVAL` are literal `0` or `1`.
`M_CLAIM_SCENARIO` is one of `accept`, `revise`, `request_evidence`, `fabricated`
or `partial`. These finite controls exercise existing deterministic approval
and citation policy; they do not confer runtime or egress authority.

Create the session from the exact plan digest, authenticate a separately
issued expiring launch scope and invoke the normal installed `claim-host`
console. Observe independent raw support, audit and claim files, inspect the
shared durable ledger and stop through an independently authenticated stop
scope. Two stable tasks share one owner with maximum two provider calls,
maximum two tasks and maximum one in flight. Preserve occupied effects and
uncertain failures for reconciliation; never rerun a partial claim trio.

## Evidence and limits

`tests/test_use_case_claim_connected.py` is the installed qualification driver;
it uses a local TLS synthetic protocol endpoint and a separate grant issuer.
The consumer and the expected raw effect oracle are separate.
The qualification schedule includes accepted and revised claims, wrong-model
and malformed/timeout responses, fabricated and partial citations, requests for more
evidence, denied host approval and duplicate task IDs. Every rejected claim
must leave support, audit and claim files absent. A between-task revoked
reference must preserve the first effect and its settled ledger charge,
refuse all second-task effects and preserve the shared task limit. Public-key signatures use
the exact hashed PEM snapshot through an owned file descriptor, including a
foreign-key path-replacement negative. A local Linux x86-64 CPython 3.13 run
with an explicit offline wheelhouse executed both parametrized cases of this
driver without a skip, and the hosted 3.13 leg lists the module in
`.github/required-installed-journeys.txt`; the use-case matrix therefore
records `qualified_offline_m_installed_shadow_protocol`. A separate missing-credential session
must refuse launch before HTTP or any claim effect. The final installed-source
drift check must refuse another plan; restoring bytes is fixture cleanup and
is followed by no further launch.
Source matching,
installed-host execution, external provider connectivity and measured benefit
are distinct evidence levels. The qualification above is an offline synthetic
protocol result only; independent review is separate and is not claimed here.

Existing off-mode upgrade/retained rollback stays qualified separately.
Connected generation transitions require the separate authenticated generation
controller and have not been advertised for M. Canary/active, live provider
connectivity, observed benefit, arbitrary claim hosts and other platforms stay
pending. Missing credentials or authentic grants fail closed.
