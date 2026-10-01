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

A new file is first written to a private `CREATE_NEW` sibling with a protected
owner-only ACL. A partial write is removed by its retained stage handle. The
stage identity and reviewed hash are durably recorded in an external intent
before its handle is renamed into the absent target without replacement. The
new target's identity, bytes, attributes and protected owner/DACL are checked.
An interrupted prepared creation removes only that exact identity; an
interrupted committed creation retains it and refuses replay. The normal implementation lifecycle
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
save, interrupted update and creation intents, and normal lifecycle rollback.
A native test also adds explicit deny ACEs with `icacls`: denying new entries
on the parent directory refuses both the staged replacement
(`windows_source_staging_copy_failed`) and an exclusive creation, and denying
`DELETE` on the file with `DELETE_CHILD` on its parent refuses the pinned
lease (`windows_source_locked_or_access_denied`). Bytes, file identity,
directory entries and the external intent location are unchanged.

A deny ACE for file data reads on a reviewed target refuses the apply with
`windows_source_read_access_denied` before any write starts; another native
read failure of a target is `windows_source_read_unavailable`. Both are
`InputError` reasons without the path or the operating-system message, and
no stage, backup or external intent is created
(`test_native_read_denied_source_refuses_apply_with_private_reason`). On
other platforms the original exception is unchanged, and `make_patch_plan`
does not use these reasons.

Before the first check of each change and again before each write, every
component of the selected relative path is compared with the entries of its
directory. Two entries that differ only by case (possible in a per-directory
case-sensitive NTFS directory), or a new name beside a differently cased
entry in such a directory, refuse the apply with
`windows_source_case_alias_refused` and no effect
(`test_native_real_case_alias_refuses_apply_without_effect`). The comparison
is the one the package-input inventory uses and folds case with Python's
`str.casefold`, not the volume's NTFS upcase table. It is a read-only listing
check, not a lock: an alias created after it is not detected.
`make_patch_plan` does not perform it.

After `icacls` (or another tool using the automatic-inheritance API) adds and
removes an ACE on a file or its parent, the file's descriptor carries
`SE_DACL_AUTO_INHERITED`. The restore now sets the inheritance-request bit
when, and only when, the recorded descriptor carries that bit, so Windows
keeps it; previously the bit was dropped and the unchanged reproducibility
check refused such a file as `windows_source_acl_not_reproducible`. The
check itself is not relaxed: the staged copy, the replacement and an owned
rollback must still show the same owner SID, DACL bytes and policy bits
(`test_native_icacls_touched_inherited_dacl_is_reproduced_exactly`, for an
ACE toggled on the file and on its parent). Known limit: a descriptor that
Windows still does not reproduce exactly remains refused with
`windows_source_acl_not_reproducible` before the source is touched. The
operator recovery step is to make the file's DACL reproducible outside this
tool, for example by re-applying the intended inherited or explicit ACL with
`icacls`, and then to run the same approved plan again; there is no override.
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
