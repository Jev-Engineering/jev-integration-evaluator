# Stopped connected generation transfer v1

This Linux x86-64 CPython 3.13 path transfers one **stopped** reviewed Alpha
connected console between separately installed source generations. The Alpha
fixture uses 1.0.2 and 1.0.3. The finite `retrieval-d-v1` fixture uses freshly
reviewed and bound 1.0.0 and 1.0.1 hosts under the same local synthetic TLS
protocol. Package and install steps
remain off mode. Transfer never
launches a console, creates provider authority, resets spend or changes the
run ID. A retained environment can be selected by a separately signed reverse
transfer. Planning requires the stopped session's existing ledger marker and
database; a missing ledger fails closed as
`connected_generation_existing_ledger_required` instead of being recreated
empty. Status and reconcile recompute the complete parent link from the
stopped session, including the original cutoff and failure history, and
refuse a child whose recorded link differs in any field.
This controller accepts the legacy Alpha profile and the finite
`retrieval-d-v1`, `retention-h-v1`, `graph-l-v1`, `claim-m-v1` and
`completion-e-v1` profiles only, and refuses a transfer between different
profiles. Composite placement and Windows generation transfer have no path
here.

Signature verification compares the exact public PEM snapshot to the
externally anchored public-key hash before inspecting P-256 or checking the
signature. Both OpenSSL operations use those same bytes. Outer path checks
alone cannot authorize a replacement key read after the path was hashed.

The host installs both generations through existing offline receipts, derives
each `connected-installed-binding-v1`, and creates fresh connected delivery
plans with exact external receipt anchors. Each version's private reference
independently signs its installed binding and egress grant. Both reference the
same owner-private ledger path and P-256 public key. The new egress grant must
end no later than the original run cutoff; a later child scope cannot extend
that cutoff.

`template connected-generation-plan` reads the stopped old session at its
externally retained journal head, checks installed source and dependency bytes
without importing target modules, reads literal `SPEC` from the installed
adapter, and derives runtime identities, placement mapping, limits and ledger
history. It writes an **unsigned** `connected-generation-transfer-v1` grant
outside the host. The private issuer signs the ASCII bytes
`generation_transfer:<grant SHA-256>` with P-256/SHA-256. Only the detached
signature and pinned public key enter the host controller.
The signed grant also binds both full delivery plan digests, so a different
valid plan sharing the same installed binding cannot inherit readiness.

`template connected-generation-transfer` requires that signed grant, exact new
plan approval, both dependency plans and the old stopped session head. It
recomputes both installed bindings and signed egress references, verifies
unchanged limits and cutoff, and creates an inert child with the same run ID
and a durable parent-head link. It then uses the one
`RuntimeLedger.transfer_generation` transaction. The ledger retains tasks,
spend, effect claims, revocation and prior generation lineage. Pending provider
reservations, uncertain effects, revoked or overrun state, drift, a live owner,
changed history, invalid mapping or failed signature block transfer.

If the controller exits after SQLite commit but before child readiness, use
`template connected-generation-status` with the same grant, signature and old
head. Its read-only result distinguishes unchanged old history, changed
history and committed receipt. Only `connected-generation-reconcile` marks an
already committed child ready; it never repeats ledger transfer or console
effect. Historical committed receipts remain readable after a later transfer,
but reconciliation requires the current ledger identity, generation grant and
history to match the selected receipt. Ledger file ownership and permissions
are checked again at this boundary. A pending child cannot launch. Later `connected-launch` still requires
its own exact current head, expiring scope and credential. Stopping and
read-only history inspection remain possible after cutoff. Retained rollback
uses a fresh signed `action=rollback` grant and another linked inert child.

The offline installed fixture uses two pinned source trees, wheel RECORD and
installed-origin maps, normal console commands, separate raw host effect
files and a local TLS synthetic protocol. It shows shared calls and closed
task tombstones through upgrade and reverse transfer. Alpha raw action effects
are stored in its fsynced host files; the ledger effect table covers explicit
`claim_effect` users. Core tests separately prove preservation of those
claims, pending-effect refusal, authority loss, external history drift and
lost commit acknowledgement.

The D fixture authors one of its two existing pinned retrieval task IDs in each
host console before the fresh scan and binder review. Its normal installed
command reads the same independently anchored corpus and writes a raw
conflict-withheld answer with ordered passage provenance. The next version
uses the second pinned task under the same two-task ledger. A signed reverse
transfer restores the retained generation identity without resetting calls or
closed-task tombstones. A normal retained console attempt writes a fixed
source-authored attempt marker before startup, then its exclusive owner marker
refuses reuse of the original effect directory. It produces no new retrieval
effect or protocol call. The ledger separately refuses a reservation for the
closed task; shadow fallback alone does not suppress the host baseline. The
profile selector, private reference names and
installed console and loader wheel origins are checked at each boundary.

The H candidate uses separately reviewed and bound 1.0.0 and 1.0.1 normal
`retention-host` commands. Each authors one of the existing two stable task IDs
before scanning and binding, and requires the explicit `/prune` choice. The
independent raw retention expectation checks pinned bytes and source provenance
in both generations. Transfers use the same two-task ledger and original
cutoff. A signed reverse transfer selects the retained generation without
resetting calls or closed tasks. Its normal console attempt uses the original
private effect directory; an exclusive host owner marker refuses a second
startup before shadow fallback can run the baseline again. A separate fixed,
source-authored attempt marker establishes command reachability. This candidate
does not yet establish executed upgrade or rollback qualification.

The L, M and E candidates
([graph](../tests/test_connected_generation_graph_installed.py),
[claim](../tests/test_connected_generation_claim_installed.py) and
[completion](../tests/test_connected_generation_completion_installed.py))
share one journey helper, `tests/connected_generation_journey.py`. Each
installs separately reviewed and bound 1.0.0 and 1.0.1 hosts of its own use
case, whose source authors one of the two existing pinned task IDs before the
scan and bind, and runs the normal installed console under the local
synthetic TLS shadow protocol. The controller change is the profile allowlist
only; the existing-ledger precondition, the profile binding check and the
complete parent-link comparison are unchanged. Each journey reads back, as
the only ledger owner after the console has exited:

- calls, cost, limits and closed-task tombstones are equal before and after
  the upgrade and after the signed reverse transfer, and the transfer receipt
  hashes match those snapshots;
- a test-authored, synthetic completed effect claim made with the real
  installed placement before planning is still present afterwards, cannot be
  claimed again through the new placement or the retained one, and an
  unmapped placement is refused. The fixture consoles record their raw
  effects in host files, so this claim is what makes the ledger effect table
  non-empty; it is not a console effect;
- a separately signed later egress grant for the new generation, a launch
  scope past the original cutoff and a clock past that cutoff are refused;
- a garbage signature, a foreign P-256 key, the issuer's signature over
  another grant digest, a correctly signed grant that is not the derived
  one, and the upgrade signature presented for the rollback are refused
  with no child and no protocol call;
- the same installed bytes relabelled to any other finite profile fail the
  plan contract, and a separately installed, valid host of another finite
  profile sharing the ledger, key, limits and cutoff is refused as
  `connected_generation_scope_invalid`;
- a child whose parent link carries a later cutoff or an added failure is
  refused by status and reconcile and cannot launch;
- the retained console attempt writes its attempt marker, is refused by the
  exclusive owner marker of the original effect directory, and produces no
  new effect and no protocol call; and
- changed installed source is refused last, after every launch.

The L raw effect is the merge receipt plus a read-only check of the
host-owned SQLite graph; M checks support, audit and released-claim bytes and
their hashes; E checks the raw state with the pinned oracle and the effect
receipt. The recipe lifecycle matrix records these three cells as
`implemented_unqualified`; the use-case matrix keeps connected upgrade
pending for every use case.

This is synthetic shadow qualification. It does not establish real provider
connectivity, observed benefit, canary/active eligibility, power-loss
durability or production activation. The controller rechecks private key and
signature references at the transaction boundary. An external revocation
exactly concurrent with a host transaction requires a trusted issuer epoch
or lease or later reconciliation. No model can grant transfer authority.
