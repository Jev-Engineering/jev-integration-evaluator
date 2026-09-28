# Python adaptation preparation v1

`instance-method-tail-call-v1` and `async-module-tail-call-v1` are separate
structural preparation contracts. They do not change the existing
`module-tail-call-v1` recipe or its strict validator. The former selects an
ordinary undecorated `Class.method(self, request)` whose only executable
statement returns `self.baseline(request)`. Its class has no bases, metaclass,
decorators, dynamic body statements or receiver attribute lookup override. The
baseline is an undecorated same-class two-argument method. The latter selects
an undecorated top-level `async def seam(request)` whose only executable
statement is `return await baseline(request)` with an unambiguous top-level
async baseline. Each accepts an optional docstring. Branches, generators,
additional statements, dynamic imports/rebindings, complex calls, keyword
arguments, signature changes and arbitrary control flow remain unsupported.

`prepare_reviewed_shape` reads the exact candidate from a complete reviewed
inventory. It requires the separately authored source-matched semantic review
and binding review, exact inventory/source/statement identities, and unchanged
bytes for every scanned source/configuration file. It returns an exact proposed
source edit and its hash without writing or importing target code. The
`adaptation-request-v1` schema is mirrored under `schemas/` and packaged data.
The current preparatory path requires one existing unambiguous static import of
the flat `adapter_name.py` module. The adapter file must be scanned and its
exact bytes named in the binding review. The selected `invoke` or
`invoke_async` callback must exist as one undecorated, correctly typed
two-argument function; missing, ambiguous and obvious placeholder callbacks
fail preparation. The caller must independently review the callback's policy
and effects before any apply operation.
An adapter hash in an untrusted request is not an approval.
The inventory and review digests must be retained and authenticated outside
the target and private preparation directory; locally matching JSON files
cannot authenticate each other.

`draft_adaptation_request` is an additive dependency on the #6 source-hashed
review context and fixed offline `RecordedReviewAdapter`. It asks the adapter
to propose only one of the two versioned shapes and an existing adapter
binding. The proposal must cite the exact selected source and callback file;
the caller supplies host policy and a separate source-matched binding review.
The resulting request binds the review context, policy, proposal and binding
review digests. The function refreshes context and source bytes and performs
structural preparation without target execution or mutation. It cannot create
missing authority callbacks. Until #6 is merged and the combined API is
qualified, tests of this seam use a synthetic module with the frozen API and
do not establish live agent-review integration.

`draft_agent_prerequisites` accepts only the fixed #6 offline adapter and
passes its proposal through `draft_prerequisite_plan`. This covers a narrower
preparatory case: two to eight
existing, exact-scoped Python files may receive appended plain top-level
helpers. Existing bytes must remain an exact prefix. Existing definitions,
imports and assignments cannot be changed; new authority-named callbacks,
decorators, evaluated defaults and annotations are rejected. The #6 context
must refresh against the actual source and retain an approved source-matched
candidate review. The proposal cites each preimage, and
an independent reviewer binds the policy, exact scope, full proposal and an
independently authored validation specification. `apply_prerequisites`
regenerates the plan before comparing it to an externally approved digest.
Its only successful state is `applied_requires_rescan`: the previous inventory,
source review and binding review become stale, and no recipe may be applied
from them. A complete new scan, #6 review and independent behavioral checks
are required before the new helpers can be used. This path does not implement
an absent approval, lock, permission or verification callback. The patch
engine guards exact source bytes and reverts ordinary write errors. Apply
creates a new private recovery bundle outside the target, archives exact
preimages and modes, fsyncs them before the first write, and journals every
write boundary. `prerequisite_status` validates the externally approved plan,
archive and full owned-file state. An interrupted or inconsistent apply returns
`blocked_recovery`; it never replays a patch or marks it verified. Preserve
the bundle for exact owned-byte recovery. `rollback_prerequisites` requires a
separate operation-bound digest and restores only owned files whose bytes and
modes still match the approved old/new identities; unrelated edits block it.
Inspect the target before any new plan.
`inspect_prerequisite_postconditions` requires an externally anchored native
runner receipt and independently authored oracle for the exact modified
files, entrypoint, schedule and attempt. It checks every recorded output,
isolation result and expected observation against the full schedule. Success
is `validated_requires_rescan`; it cannot make the old inventory or recipe
applicable. The dedicated privileged CI job executes a synthetic host that
imports both newly added helpers from the modified files and checks their
effects and result. This is synthetic qualification of the bounded path, not
evidence that an arbitrary host policy or callback is safe.

The synthetic structural tests execute the original and proposed method or
async function with an inert local adapter. They check receiver state, effect
order, return/exception behavior, await count and cancellation. These tests
exercise the shape edit; they do not qualify active JEV routing, a generated
adapter or a real host integration. The separate native lifecycle tests below
exercise patch application and isolation with an inert synthetic adapter.
`host.invoke_bound` is synchronous and cannot safely run an async executor;
the async strategy must get a distinct independently verified runtime before
it can be promoted to an executable recipe. Preparatory prerequisites also
need a fresh source scan and candidate/binding reviews after their changes.

## Native one-source lifecycle

`plan_adaptation` writes a private, versioned exact-byte bundle outside the
target. It owns only the selected source file and retains its UTF-8 preimage.
The plan binds both source and existing adapter modes as well as their bytes;
native baseline and modified manifests must match those modes.
Loading the bundle rechecks private ownership and modes, reviewed candidate
and adapter identities, and regenerates the edit and diff from the archived
preimage. A self-consistent rewrite of local plan and patch files cannot
substitute a different source edit.
`apply_adaptation` requires externally approved exact plan identity and an
externally anchored native baseline receipt with independent pre-edit
postconditions. It refuses source or adapter drift, then writes through the
guarded patch engine and fsynced journal. `verify_adaptation` requires the
separately anchored modified receipt and an independent baseline/off/shadow
oracle bound to repository, review context and bundle. It reports fresh
verification only after actual edited-host execution; a later read-only status
returns `applied_unverified` because local journal entries do not authenticate
private output bytes. An interrupted apply returns `blocked_recovery`; exact
owned-byte rollback requires a separate operation-bound digest. These calls do not run the target,
allocate execution authority or confer deployment/activation approval.

The privileged hosted synthetic tests run both method and async edited hosts
inside the native isolated Python runner. Their inert adapter exercises call
and await semantics, including off/shadow parity. Separate tests check async
cancellation and exception propagation. This is a bounded adaptation path,
not arbitrary Python rewriting or a JEV provider activation claim.
