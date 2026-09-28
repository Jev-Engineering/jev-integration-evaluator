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
`apply_adaptation` requires externally approved exact plan identity and an
externally anchored native baseline receipt with independent pre-edit
postconditions. It refuses source or adapter drift, then writes through the
guarded patch engine and fsynced journal. `verify_adaptation` requires the
separately anchored modified receipt and an independent baseline/off/shadow
oracle bound to repository, review context and bundle. It reports fresh
verification only after actual edited-host execution; a later read-only status
returns `applied_unverified` because local journal entries do not authenticate
private output bytes. An interrupted apply returns `blocked_recovery`; exact
owned-byte rollback remains available. These calls do not run the target,
allocate execution authority or confer deployment/activation approval.

The privileged hosted synthetic tests run both method and async edited hosts
inside the native isolated Python runner. Their inert adapter exercises call
and await semantics, including off/shadow parity. Separate tests check async
cancellation and exception propagation. This is a bounded adaptation path,
not arbitrary Python rewriting or a JEV provider activation claim.
