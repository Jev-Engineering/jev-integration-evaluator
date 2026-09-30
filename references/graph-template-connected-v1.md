# L graph installed shadow protocol

This finite Linux x86-64 CPython 3.13 checkpoint extends the [source-bound L
offline journey](graph-template-offline-v1.md). It binds the reviewed
`graph_host/host_graph_consumer.py` task loop, generated adapter, normal installed
`graph-host` console and host-owned public-only `connected_authority.py` to the
same fresh package/install receipts and wheel RECORD origins. The independent
test is [test_use_case_graph_connected.py](../tests/test_use_case_graph_connected.py).
The original graph entity module and SQLite consumer remain pinned and unchanged.

After the off-mode bind, apply, verify, package and install steps, derive an
installed binding with the exact package and install receipt hashes. Use
`template connected-plan --host-profile graph-l-v1` with that binding, a private
launch-environment JSON file and a separately authored observation JSON file.
Then use `template connected-configure`, `connected-launch`, `connected-status`
and `connected-stop` with exact plan/session/scope hashes as described in
[connected delivery](connected-delivery-v1.md). Package and install remain off.
The connected plan itself cannot authorize execution or egress.

| Launch input | Finite meaning |
| --- | --- |
| `L_CONNECTED_REF`, `L_AUTH_PUBKEY_FILE` | Owner-private descriptor and independently pinned P-256 public issuer key. Their bytes are hashed in the plan and injected as `L_CONNECTED_REF_SHA256` and `L_AUTH_PUBKEY_SHA256`. The signing key never enters the host. |
| `GRAPH_DB_PATH` | One owner-private SQLite database for both task effects. The host checks exact entities, revision, prior audit and merge receipts, then commits audit and merge in one transaction. |
| `GRAPH_EFFECT_PATH`, `GRAPH_SECOND_EFFECT_PATH` | Distinct fresh owner-private raw effect files, one per task. |
| `GRAPH_READY_PATH`, `L_HOLD`, `L_RELEASE_PATH` | First-effect readback marker and optional finite hold (`0` or `1`) before the second task. A held run has a 15-second limit. |
| `L_TASKS` | `two` for stable `graph-one`/`graph-two` IDs; `duplicate` is rejected by generated task ownership before runtime startup. |
| `L_APPROVAL`, `L_EXPECTED_REVISION` | Code-owned oracle controls (`0` or `1`) for denied approval and initial revision conflict; they do not grant authority. |
| `SSL_CERT_FILE` | Optional private local TLS trust anchor, hashed in the plan. |

The installed synthetic test runs two real task calls through one generated
console and one durable ledger. It reads the external SQLite rows and effect
files independently: revision 1 and 2, exact entity provenance, audit and
merge receipts, and the baseline effects under wrong-model fallback. A held
first local TLS response demonstrates the one-in-flight budget; duplicate task,
missing credential/reference, wrong scope key, reference/source drift, denied
approval and revision conflict fail closed. The fixture uses model
`jev-1.13.0`. Revoking the owner-private reference after the first committed
effect retains that raw effect and blocks the second task before provider I/O.
The fixture uses
a local TypeSafe-shaped TLS server and a dummy credential. Its
issuer is synthetic; no external JEV provider, spend or benefit is observed.

Omitting `--host-profile` retains the original Alpha plan bytes. D and dual
profiles have separate names and source origins. Canary and active modes remain
closed without independently authenticated observed gates. Existing off-mode
upgrade and rollback are separate from connected generation transfer, which is
pending for this L fixture. Arbitrary graphs, approval policies, task loops and
unreviewed retrievers are outside this finite qualification.
