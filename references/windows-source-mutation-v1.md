# Native Windows reviewed source mutation

`apply_patch_plan` retains its exact approved plan digest and original CLI
contract. On native Windows, a mutation is limited to a local NTFS drive-letter
path. Each lexical ancestor is checked and pinned; a source reparse point,
hardlink, read-only file, locked writer, stale content hash or changed identity
is refused. This is an ownership boundary for a cooperative local host, not an
OS sandbox or a compare-and-swap primitive against an adversarial process.

For an update, the writer copies the source to a private sibling so its named
streams and file attributes are retained, then writes bounded UTF-8 bytes.
It verifies that the source owner, DACL bytes and policy bits can be reproduced.
The source handle pins its NTFS identity and denies peer deletion. An external
owner-private intent records the reviewed hashes and file identities, without
source bytes or security descriptors. The writer then renames that handle to
an owned backup and renames the staged handle into the vacated name. Both
renames refuse an existing destination. It checks the resulting identities,
bytes, attributes, mode and owner/DACL before deleting the backup by handle.

An interrupted prepared intent restores the original only when the retained
backup identity and bytes match and the destination is vacant or belongs to
the staged identity. A committed intent keeps the reviewed new file and only
cleans up the matching backup. Recovery stops the renewed apply for review;
it never replays the patch. A peer's file in the destination is preserved and
requires external reconciliation. The intent lives outside the approved source
tree; an unknown intent, identity or recovery state fails closed. This protocol
does not claim an atomic multi-file transaction or a general compare-and-swap.

A new file uses `CREATE_NEW` and a protected owner-only ACL. A partial write is
removed by its retained creation handle. The normal implementation lifecycle
records each applied NTFS identity in its sealed journal. Its rollback removes
an owned creation by handle only when identity and expected bytes still match;
an update rollback requires the retained applied identity before making a new
reviewed replacement. A same-content peer replacement is retained. Windows
path duplicates are compared without case. Successful update rollback restores
reviewed bytes and owner/DACL through a new replacement; it does not claim the
original NTFS file ID. Missing Windows identity in an older journal is a
rollback refusal, not inferred ownership.

The owner/DACL comparison hashes the owner SID, exact DACL bytes and DACL
present, defaulted, inheritance-request, inherited and protection bits. It
requires a revision-one self-relative descriptor and excludes unrelated security
descriptor layout and group fields, which Windows can reserialize while the
owner/DACL remains unchanged. The native tests cover ordinary inherited and
protected ACLs separately, a hidden attribute, a named stream, peer atomic
save, interrupted intents and normal lifecycle rollback.
Other metadata and access-control forms need their own native qualification.
There is no provider call, target execution or
activation in this source mutation step.

Example with synthetic temporary source:

```python
from jev_integration_evaluator.implementation import make_patch_plan, apply_patch_plan

plan = make_patch_plan(disposable_root,
                       [{'file': 'example.py', 'new_content': 'value = 2\n'}],
                       ['reviewed-example'])
# A separate trusted operator reviews the full diff and approves plan_digest.
result = apply_patch_plan(disposable_root, plan, plan['plan_digest'])
assert result['status'] == 'applied'
```

This example illustrates the API shape only; it is not an approval mechanism.
