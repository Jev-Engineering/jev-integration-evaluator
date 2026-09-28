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
exact bytes named in the binding review. The caller must independently review
that code before any apply operation.
An adapter hash in an untrusted request is not an approval.
The inventory and review digests must be retained and authenticated outside
the target and private preparation directory; locally matching JSON files
cannot authenticate each other.

The synthetic structural tests execute the original and proposed method or
async function with an inert local adapter. They check receiver state, effect
order, return/exception behavior, await count and cancellation. These tests
exercise the shape edit; they do not qualify active JEV routing, the generated
adapter, patch application, native isolation or a real host integration.
`host.invoke_bound` is synchronous and cannot safely run an async executor;
the async strategy must get a distinct independently verified runtime before
it can be promoted to an executable recipe. Preparatory prerequisites also
need a fresh source scan and candidate/binding reviews after their changes.
