# D retrieval installed shadow protocol

This checkpoint extends the [source-bound D offline journey](retrieval-template-offline-v1.md)
on Linux x86-64 CPython 3.13. The reviewed `retrieval_host` source adds a
code-owned `connected_authority.py` before its final fresh scan and binding.
The same reviewed binder supplies the exact task-loop adapter; no generated
source is hand-edited. Baseline and modified verification, offline package and
install, wheel RECORD origins and the normal installed `retrieval-host` command
are exercised in `tests/test_use_case_retrieval_connected.py`.

`template connected-plan --host-profile retrieval-d-v1` selects the finite D
profile. Its plan binds the installed source, console and loader origins,
external corpus bytes, owner-private reference, public issuer key and optional
local TLS certificate by hash. A profile does not grant egress. The external
issuer signs the exact installed binding and shadow egress grant; only its
public key enters the child. A separate expiring session scope binds the plan
hash and public key. Omitting `--host-profile` retains the original Alpha plan
representation and approval digest. Cross-profile reference names and source
origins are rejected.

The installed synthetic test uses a local TLS TypeSafe protocol fixture and
dummy startup credential. It observes the first and second task effects from
separate external files, checks the pinned corpus revision and passage/source/
span provenance, and verifies that conflicting status evidence withholds the
answer. A wrong-model response leaves the same baseline consumer effects.
The test also checks reference drift, wrong-key scope and exact owned stop.

Three further schedules use the finite `D_HOLD_POINT` launch selector. Its
values are `pre-commit` (the default: hold inside the second task before its
commit) and `between-tasks` (hold after the first committed effect and before
the second task routes). `between-tasks` requires `D_HOLD` `1` and
`D_RELEASE_PATH`; any other value or combination is refused at planning with
`connected_host_references_required`. With the between-task hold the test
reads back exactly one provider attempt and one settled ledger reservation
before it releases the second task:

- **Malformed response.** The local endpoint returns bytes that are not JSON.
  Both tasks still write the same withheld-conflict effect bytes as the valid
  run, the host audit records one `JSONDecodeError` assessment error per task,
  and the ledger holds exactly two calls.
- **Actual timeout.** The endpoint answers after the adapter's 2000 ms
  transport budget. Both effects are again byte-identical to the valid run,
  the audit records one `EvaluationTimeoutError` per task, and the ledger
  holds exactly two calls. A timed-out reservation is not refunded.
- **Between-task revocation.** The owner-private reference is changed while
  the host is held. The first effect and its single ledger charge remain; the
  second task stops before its route, so there is no second effect, no ready
  marker and no second provider attempt.

An assessment failure never changes the host effect: the D host keeps its
deterministic baseline selection and the answer stays withheld.
These fixture requests are not a live provider call, and their token counts
are not a spending or benefit measurement.

The separate D off-mode test establishes version 1.0.1 package upgrade,
retained-generation rollback and owned source rollback. The
[stopped connected generation path](connected-generation-transfer-v1.md)
adds a finite two-version synthetic shadow transfer under one ledger and
original cutoff; it requires independently signed installed and egress
references for both versions and an exact signed transfer grant. The Linux
installed fixture runs normal commands for both versions and the retained
owner-refused replay. External
endpoint/model grant, actual credential authority, observed canary/active gates
and live benefit remain pending. The finite fixture does not qualify arbitrary
retrievers, queries or a generative answer model.
