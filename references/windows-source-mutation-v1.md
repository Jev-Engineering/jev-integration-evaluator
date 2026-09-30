# Native Windows reviewed source mutation

`apply_patch_plan` retains its exact approved plan digest and original CLI
contract. On native Windows, a mutation is limited to a local NTFS drive-letter
path. Each lexical ancestor is checked and pinned; a source reparse point,
hardlink, read-only file, locked writer, stale content hash or changed identity
is refused. This is an ownership boundary for a cooperative local host, not an
OS sandbox or a compare-and-swap primitive against an adversarial process.

For an update, the writer stages bounded UTF-8 bytes in a private sibling,
verifies that the source owner and exact DACL bytes and policy bits can be
reproduced, then uses `ReplaceFileW` with an original-file backup. It checks
source and backup NTFS identities, new bytes and owner/DACL before removing the
backup. If a post-replacement check fails, it restores the backup only while
both paths still have the expected identities, then checks restored bytes and
owner/DACL. Unknown identities or an unavailable recovery operation leave the
backup and report recovery required; they never authorize another write.

A new file uses `CREATE_NEW` and a protected owner-only ACL. After a later
transaction failure, rollback deletes that file by its open handle only when
its NTFS identity and exact expected bytes still match. Updates likewise bind
rollback to the replacement's identity and content. A same-content concurrent
replacement is retained. Windows path duplicates are compared without case.
Successful rollback of an update restores reviewed bytes and owner/DACL through
a new replacement; it does not claim the original NTFS file ID.

The owner/DACL comparison hashes the owner SID, exact DACL bytes and DACL
present, defaulted, inheritance-request, inherited and protection bits. It
requires a revision-one self-relative descriptor and excludes unrelated security
descriptor layout and group fields, which Windows can reserialize while the
owner/DACL remains unchanged. The native tests cover ordinary inherited and
protected ACLs separately, plus one hidden attribute and one named stream.
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
