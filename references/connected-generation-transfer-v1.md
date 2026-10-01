# Stopped connected generation transfer v1

This Linux x86-64 CPython 3.13 path transfers one **stopped** reviewed Alpha
connected console between separately installed 1.0.2 and 1.0.3 source
generations. The package and install steps remain off mode. Transfer never
launches a console, creates provider authority, resets spend or changes the
run ID. A retained environment can be selected by a separately signed reverse
transfer. Planning requires the stopped session's existing ledger marker and
database; a missing ledger fails closed as
`connected_generation_existing_ledger_required` instead of being recreated
empty. This controller accepts only the legacy Alpha profile; D retrieval,
composite placement and Windows generation transfer have no qualified path here.

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

This is synthetic shadow qualification. It does not establish real provider
connectivity, observed benefit, canary/active eligibility, power-loss
durability or production activation. The controller rechecks private key and
signature references at the transaction boundary. An external revocation
exactly concurrent with a host transaction requires a trusted issuer epoch
or lease or later reconciliation. No model can grant transfer authority.
