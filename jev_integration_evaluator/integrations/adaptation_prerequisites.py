"""Bounded reviewed multi-file Python prerequisites; never grants runtime authority."""
from __future__ import annotations

import ast
import hashlib
import os
import re
import stat
from pathlib import Path

from ..implementation import apply_patch_plan, make_patch_plan
from ..contracts import validate_contract
from ..io import InputError, digest, file_hash, read_json, safe_child, write_json
from ..runners.isolated_python import RunnerError, canonical, inspect_receipt, request_digest
from ..runners.observations import _observation
from .lifecycle import _bundle_dir, _journal, _lock, _record, _sync_dir


AUTHORITY = re.compile(r'(?i)(approv|authoriz|permission|verif|validat|lock|guard|policy|allow|deny|authenticat)')


def _safe_additions(old: bytes, new: str) -> None:
    """Permit only new plain top-level helpers; preserve all existing AST nodes."""
    try:
        before = ast.parse(old.decode('utf-8'))
        after = ast.parse(new)
    except (UnicodeError, SyntaxError):
        raise InputError('Prerequisite requires valid UTF-8 Python') from None
    if not new.encode('utf-8').startswith(old):
        raise InputError('Prerequisite may only append after unchanged source bytes')
    if len(after.body) <= len(before.body):
        raise InputError('Prerequisite must add a helper')
    for prior, current in zip(before.body, after.body):
        if ast.dump(prior, include_attributes=False) != ast.dump(current, include_attributes=False):
            raise InputError('Prerequisite cannot alter existing definitions')
    existing = {n.name for n in before.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    # A new module global can shadow a builtin or late-bound global used by
    # existing code even when it was never assigned in this module.
    existing.update(n.id for n in ast.walk(before) if isinstance(n, ast.Name))
    for node in before.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            existing.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
    added = set()
    for node in after.body[len(before.body):]:
        if (not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                or node.decorator_list or node.name in existing or node.name in added
                or node.name.startswith('_') or AUTHORITY.search(node.name)
                or node.returns is not None or getattr(node, 'type_params', ())
                or node.args.defaults or any(x is not None for x in node.args.kw_defaults)
                or any(x.annotation is not None for x in
                       node.args.posonlyargs + node.args.args + node.args.kwonlyargs)
                or (node.args.vararg is not None and node.args.vararg.annotation is not None)
                or (node.args.kwarg is not None and node.args.kwarg.annotation is not None)):
            raise InputError('Prerequisite cannot add authority or dynamic bindings')
        added.add(node.name)


def draft_prerequisite_plan(root, inventory, context, proposal, *, host_policy,
                            trusted_review, allowed_files, validation_spec,
                            related_files=(), capability_report=None, discovery_excludes=None):
    """Build an exact plan from independently reviewed append-only helpers."""
    root = Path(root).resolve(strict=True)
    try:
        from ..agent_review import retrieve_context
    except ImportError:
        raise InputError('Agent review dependency is not merged') from None
    fresh_context = retrieve_context(root, inventory, context['candidate_id'],
                                     related_files=related_files,
                                     capability_report=capability_report,
                                     discovery_excludes=discovery_excludes)
    if fresh_context != context:
        raise InputError('Prerequisite context changed after review')
    candidates = [row for row in inventory.get('candidates', [])
                  if row.get('candidate_id') == context['candidate_id']]
    if (len(candidates) != 1 or candidates[0].get('tier') == 0
            or candidates[0].get('pattern') == 'NONE'
            or candidates[0].get('hard_real_time') is True
            or candidates[0].get('deterministic_alternative') in ('mandatory','preferred')
            or candidates[0].get('semantic_review', {}).get('approved') is not True
            or candidates[0]['semantic_review'].get('source_sha256') != context.get('source_sha256')
            or not candidates[0]['semantic_review'].get('reviewer')
            or not candidates[0]['semantic_review'].get('reason')
            or candidates[0].get('source', {}).get('source_sha256') != context.get('source_sha256')
            or len([row for row in context.get('sources', [])
                    if row['file'] == candidates[0]['source'].get('file')
                    and row['sha256'] == candidates[0]['source'].get('file_sha256')]) != 1):
        raise InputError('Source-matched candidate review required for prerequisites')
    if (type(allowed_files) not in (list, tuple)
            or any(type(name) is not str for name in allowed_files)):
        raise InputError('Exact prerequisite scope required')
    validate_contract(proposal, 'offline-adaptation-prerequisites-v1')
    validate_contract(validation_spec, 'prerequisite-validation-v1')
    agent_request = {'context':context, 'policy_sha256':digest(host_policy),
                     'allowed_files':sorted(allowed_files),
                     'authority':{'mutation':False,'execution':False,'egress':False}}
    if (type(proposal) is not dict or set(proposal) != {'schema_version','kind','request_sha256','context_sha256','policy_sha256','changes'}
            or proposal['kind'] != 'adaptation-prerequisites-v1'
            or proposal['request_sha256'] != digest(agent_request)
            or proposal['context_sha256'] != digest(context)
            or proposal['policy_sha256'] != digest(host_policy)
            or type(host_policy) is not dict or not host_policy
            or type(validation_spec) is not dict or not validation_spec
            or context.get('inventory_sha256') != digest(inventory)):
        raise InputError('Prerequisite proposal differs from reviewed context or policy')
    changes = proposal['changes']
    if type(changes) is not list or not 2 <= len(changes) <= 8:
        raise InputError('Prerequisite requires two to eight scoped files')
    if type(allowed_files) not in (list, tuple) or len(allowed_files) != len(changes):
        raise InputError('Exact prerequisite scope required')
    names = [row.get('file') for row in changes if type(row) is dict]
    if (len(names) != len(changes) or len(set(names)) != len(names)
            or set(names) != set(allowed_files)):
        raise InputError('Prerequisite files differ from exact scope')
    context_files = {row['file']: row['sha256'] for row in context['sources']}
    inventory_files = {row['file']: row['sha256'] for row in inventory['files']}
    for row in changes:
        if (set(row) != {'file','old_sha256','new_content'}
                or type(row['file']) is not str or not row['file'].endswith('.py')
                or type(row['new_content']) is not str
                or len(row['new_content'].encode('utf-8')) > 120_000
                or row['old_sha256'] != context_files.get(row['file'])
                or row['old_sha256'] != inventory_files.get(row['file'])):
            raise InputError('Prerequisite change lacks exact reviewed source')
        path = safe_child(root, row['file'])
        if not path.is_file() or file_hash(path) != row['old_sha256']:
            raise InputError('Prerequisite source changed after review')
        _safe_additions(path.read_bytes(), row['new_content'])
    case_ids = [row['case_id'] for row in validation_spec['cases']]
    if len(set(case_ids)) != len(case_ids):
        raise InputError('Duplicate prerequisite validation case')
    inventory_files = {row['file']:row['sha256'] for row in inventory['files']}
    for case in validation_spec['cases']:
        entry = safe_child(root, case['entry'])
        if (case['entry'] in names or not entry.is_file()
                or inventory_files.get(case['entry']) != case['entry_sha256']
                or file_hash(entry) != case['entry_sha256']):
            raise InputError('Prerequisite validation entry differs from reviewed snapshot')
        try:
            _observation(canonical(case['observation']) + b'\n')
        except RunnerError:
            raise InputError('Invalid independent prerequisite expected observation') from None
    expected = {'approved','proposal_sha256','context_sha256','policy_sha256',
                'scope_sha256','validation_sha256','reviewer','reason'}
    if (type(trusted_review) is not dict or set(trusted_review) != expected
            or trusted_review['approved'] is not True
            or trusted_review['proposal_sha256'] != digest(proposal)
            or trusted_review['context_sha256'] != digest(context)
            or trusted_review['policy_sha256'] != digest(host_policy)
            or trusted_review['scope_sha256'] != digest(sorted(allowed_files))
            or trusted_review['validation_sha256'] != digest(validation_spec)
            or not trusted_review['reviewer'] or not trusted_review['reason']):
        raise InputError('Independent prerequisite and validation review required')
    patch = make_patch_plan(root, [{'file':row['file'],'new_content':row['new_content']}
                                   for row in changes], [context['candidate_id']])
    owned = [{'file':row['file'], 'old_sha256':row['old_sha256'],
              'new_sha256':row['new_sha256'],
              'mode':stat.S_IMODE(safe_child(root, row['file']).stat().st_mode),
              'preimage':f'preimages/{index}.utf8'}
             for index, row in enumerate(patch['changes'])]
    identity = root.stat()
    binding = {'schema_version':'1.0', 'kind':'adaptation-prerequisite-plan-v1',
               'root_device': identity.st_dev, 'root_inode': identity.st_ino,
               'inventory_sha256':digest(inventory), 'context_sha256':digest(context),
               'policy_sha256':digest(host_policy), 'proposal_sha256':digest(proposal),
               'review_sha256':digest(trusted_review), 'scope_sha256':digest(sorted(allowed_files)),
               'patch_sha256':digest(patch), 'owned_sha256':digest(owned),
               'validation_sha256':digest(validation_spec)}
    validate_contract(binding, 'adaptation-prerequisite-plan-v1')
    return {'status':'planned_prerequisites','binding':binding,'patch':patch,'owned':owned,
            'contract_digest':digest(binding),'target_modified':False}


def draft_agent_prerequisites(root, inventory, context, adapter, *, host_policy,
                              trusted_review, allowed_files, validation_spec,
                              related_files=(), capability_report=None, discovery_excludes=None):
    """Obtain a fixed offline agent proposal, then subject it to exact review."""
    try:
        from ..agent_review import RecordedReviewAdapter, retrieve_context
    except ImportError:
        raise InputError('Agent review dependency is not merged') from None
    if type(adapter) is not RecordedReviewAdapter:
        raise InputError('Only the fixed offline review adapter is supported')
    if (type(allowed_files) not in (list, tuple)
            or any(type(name) is not str for name in allowed_files)):
        raise InputError('Exact prerequisite scope required')
    fresh = retrieve_context(Path(root), inventory, context['candidate_id'],
                             related_files=related_files,
                             capability_report=capability_report,
                             discovery_excludes=discovery_excludes)
    if fresh != context:
        raise InputError('Prerequisite context changed before agent proposal')
    request = {'context':context, 'policy_sha256':digest(host_policy),
               'allowed_files':sorted(allowed_files),
               'authority':{'mutation':False,'execution':False,'egress':False}}
    proposal = adapter.respond(request)
    return draft_prerequisite_plan(root, inventory, context, proposal,
                                   host_policy=host_policy, trusted_review=trusted_review,
                                   allowed_files=allowed_files, validation_spec=validation_spec,
                                   related_files=related_files,
                                   capability_report=capability_report,
                                   discovery_excludes=discovery_excludes)


def apply_prerequisites(root, plan, approved_digest, *, inventory, context, proposal,
                        host_policy, trusted_review, allowed_files, validation_spec,
                        recovery_bundle, related_files=(), capability_report=None,
                        discovery_excludes=None):
    """Apply only a freshly regenerated, externally approved patch; require rescan."""
    fresh = draft_prerequisite_plan(root, inventory, context, proposal,
                                    host_policy=host_policy, trusted_review=trusted_review,
                                    allowed_files=allowed_files, validation_spec=validation_spec,
                                    related_files=related_files, capability_report=capability_report,
                                    discovery_excludes=discovery_excludes)
    if plan != fresh or approved_digest != fresh['contract_digest']:
        raise InputError('Externally approved exact prerequisite plan required')
    root = Path(root).resolve(strict=True)
    bundle = _bundle_dir(recovery_bundle)
    if bundle == root or bundle.is_relative_to(root) or bundle.exists():
        raise InputError('Prerequisite recovery bundle needs a new external directory')
    bundle.mkdir(parents=True, mode=0o700)
    os.chmod(bundle, 0o700)
    owned = fresh['owned']
    preimages = safe_child(bundle, 'preimages')
    preimages.mkdir(mode=0o700)
    for index, row in enumerate(fresh['patch']['changes']):
        path = safe_child(root, row['file'])
        raw = path.read_bytes()
        if file_hash(path) != row['old_sha256']:
            raise InputError('Prerequisite changed while archiving preimages')
        relative = owned[index]['preimage']
        archive = safe_child(bundle, relative)
        with archive.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.chmod(archive, 0o600)
        if stat.S_IMODE(path.stat().st_mode) != owned[index]['mode']:
            raise InputError('Prerequisite mode changed while archiving preimages')
    archive_plan = {'schema_version':'1.0', 'kind':'adaptation-prerequisite-recovery-v1',
                    'contract_digest':fresh['contract_digest'], 'binding':fresh['binding'],
                    'patch':fresh['patch'], 'owned':owned}
    write_json(safe_child(bundle, 'recovery-plan.json'), archive_plan)
    os.chmod(safe_child(bundle, 'recovery-plan.json'), 0o600)
    _sync_dir(preimages); _sync_dir(bundle)
    with _lock(bundle):
        _record(bundle, archive_plan, 'apply_started')
        def progress(event, change):
            if event == 'write_completed': _sync_dir(safe_child(root, change['file']).parent)
            _record(bundle, archive_plan, 'apply_'+event, change['file'])
        try:
            applied = apply_patch_plan(root, fresh['patch'], fresh['patch']['plan_digest'],
                                       progress=progress)
        except Exception:
            _record(bundle, archive_plan, 'apply_failed_recovery_required')
            raise
        if any(file_hash(safe_child(root, row['file'])) != row['new_sha256']
               or stat.S_IMODE(safe_child(root, row['file']).stat().st_mode) != row['mode']
               for row in owned):
            _record(bundle, archive_plan, 'apply_identity_failed')
            raise InputError('Prerequisite bytes or modes changed during apply')
        _record(bundle, archive_plan, 'applied_requires_rescan')
        return {'status':'applied_requires_rescan', 'contract_digest':approved_digest,
                'files':applied['files'], 'verified':False, 'recipe_applicable':False,
                'recovery_bundle':str(bundle)}


def prerequisite_status(root, recovery_bundle, approved_digest):
    """Read-only recovery state; never replay or authenticate behavior."""
    root = Path(root).resolve(strict=True)
    bundle = _bundle_dir(recovery_bundle)
    if bundle == root or bundle.is_relative_to(root):
        raise InputError('Unsafe prerequisite recovery bundle')
    if os.name == 'posix' and (stat.S_IMODE(bundle.stat().st_mode) != 0o700
                               or bundle.stat().st_uid != os.geteuid()):
        raise InputError('Unsafe prerequisite recovery ownership or mode')
    archive = safe_child(bundle, 'recovery-plan.json')
    if not archive.is_file() or (os.name == 'posix' and
                                (stat.S_IMODE(archive.stat().st_mode) != 0o600
                                 or archive.stat().st_uid != os.geteuid())):
        raise InputError('Unsafe prerequisite recovery plan')
    plan = read_json(archive)
    root_stat = root.stat()
    if (plan.get('kind') != 'adaptation-prerequisite-recovery-v1'
            or plan.get('contract_digest') != approved_digest
            or digest(plan.get('binding')) != approved_digest
            or digest(plan.get('patch')) != plan['binding']['patch_sha256']
            or digest(plan.get('owned')) != plan['binding']['owned_sha256']
            or digest({k:v for k,v in plan['patch'].items() if k != 'plan_digest'})
               != plan['patch']['plan_digest']
            or plan['binding']['root_device'] != root_stat.st_dev
            or plan['binding']['root_inode'] != root_stat.st_ino
            or len(plan['owned']) != len(plan['patch']['changes'])
            or any(row['file'] != change['file']
                   or row['old_sha256'] != change['old_sha256']
                   or row['new_sha256'] != change['new_sha256']
                   or row['preimage'] != f'preimages/{index}.utf8'
                   for index, (row, change) in enumerate(zip(
                       plan['owned'], plan['patch']['changes'])))):
        raise InputError('Prerequisite recovery identity mismatch')
    for row in plan['owned']:
        path = safe_child(bundle, row['preimage'])
        if (not path.is_file() or file_hash(path) != row['old_sha256']
                or (os.name == 'posix' and (stat.S_IMODE(path.stat().st_mode) != 0o600
                                           or path.stat().st_uid != os.geteuid()))):
            raise InputError('Prerequisite preimage archive changed')
    events = [row['event'] for row in _journal(bundle, plan)]
    current = []
    for row in plan['owned']:
        path = safe_child(root, row['file'])
        current.append((file_hash(path), stat.S_IMODE(path.stat().st_mode))
                       if path.is_file() else (None, None))
    if events and events[-1] == 'rolled_back' and all(
            actual == (row['old_sha256'], row['mode']) for actual, row in zip(current, plan['owned'])):
        return {'status':'rolled_back', 'verified':False, 'recipe_applicable':False,
                'contract_digest':approved_digest}
    if events and events[-1] == 'applied_requires_rescan' and all(
            actual == (row['new_sha256'], row['mode']) for actual, row in zip(current, plan['owned'])):
        return {'status':'applied_requires_rescan', 'verified':False,
                'recipe_applicable':False, 'contract_digest':approved_digest}
    return {'status':'blocked_recovery', 'verified':False, 'recipe_applicable':False,
            'contract_digest':approved_digest}


def prerequisite_rollback_digest(contract_digest, owned_sha256):
    return digest({'operation':'restore_owned_prerequisite_preimages',
                   'contract_digest':contract_digest, 'owned_sha256':owned_sha256})


def rollback_prerequisites(root, recovery_bundle, approved_digest, rollback_approval):
    """Restore only exact owned old/new bytes under a distinct approval."""
    root = Path(root).resolve(strict=True)
    bundle = _bundle_dir(recovery_bundle)
    # Validates external plan anchor, private preimages, journal and root identity.
    prerequisite_status(root, bundle, approved_digest)
    plan = read_json(safe_child(bundle, 'recovery-plan.json'))
    if rollback_approval != prerequisite_rollback_digest(
            approved_digest, plan['binding']['owned_sha256']):
        raise InputError('Separate exact prerequisite rollback approval required')
    with _lock(bundle):
        state = prerequisite_status(root, bundle, approved_digest)
        if state['status'] == 'rolled_back':
            return {'status':'rolled_back', 'idempotent':True}
        restores = []
        for row in plan['owned']:
            path = safe_child(root, row['file'])
            if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != row['mode']:
                raise InputError('Prerequisite rollback refuses owned mode or path drift')
            actual = file_hash(path)
            if actual not in (row['old_sha256'], row['new_sha256']):
                raise InputError('Prerequisite rollback refuses unrelated owned edits')
            if actual == row['new_sha256']:
                restores.append({'file':row['file'], 'new_content':
                                 safe_child(bundle, row['preimage']).read_bytes().decode('utf-8')})
        _record(bundle, plan, 'rollback_started')
        if restores:
            patch = make_patch_plan(root, restores, plan['patch']['candidate_ids'])
            def progress(event, change):
                if event == 'write_completed': _sync_dir(safe_child(root, change['file']).parent)
                _record(bundle, plan, 'rollback_'+event, change['file'])
            try:
                apply_patch_plan(root, patch, patch['plan_digest'], progress=progress)
            except Exception:
                _record(bundle, plan, 'rollback_failed_recovery_required')
                raise
        if any(file_hash(safe_child(root, row['file'])) != row['old_sha256']
               or stat.S_IMODE(safe_child(root, row['file']).stat().st_mode) != row['mode']
               for row in plan['owned']):
            _record(bundle, plan, 'rollback_identity_failed')
            raise InputError('Prerequisite rollback did not restore owned identities')
        _record(bundle, plan, 'rolled_back')
        return {'status':'rolled_back','restored_files':len(restores),
                'unrelated_paths_modified':False}


def inspect_prerequisite_postconditions(root, recovery_bundle, approved_digest, *,
                                        spec, receipt, outputs, oracle, validation_spec,
                                        trusted_oracle_sha256,
                                        trusted_receipt_sha256):
    """Check independent native helper outcomes; leave all old reviews stale."""
    root = Path(root).resolve(strict=True)
    state = prerequisite_status(root, recovery_bundle, approved_digest)
    if state['status'] != 'applied_requires_rescan':
        raise InputError('Prerequisite recovery state is not complete')
    plan = read_json(safe_child(_bundle_dir(recovery_bundle), 'recovery-plan.json'))
    validate_contract(validation_spec, 'prerequisite-validation-v1')
    if digest(validation_spec) != plan['binding']['validation_sha256']:
        raise InputError('Native prerequisite validation differs from reviewed expectations')
    root_stat = root.stat()
    if spec.get('source_identity') != {'device':root_stat.st_dev, 'inode':root_stat.st_ino}:
        raise InputError('Native prerequisite proof belongs to another source root')
    for row in plan['owned']:
        matches = [item for item in spec['files'] if item['path'] == row['file']]
        if len(matches) != 1 or matches[0]['sha256'] != row['new_sha256'] or matches[0]['mode'] != row['mode']:
            raise InputError('Native prerequisite proof omits exact modified source')
    if (type(oracle) is not dict or set(oracle) != {
            'schema_version','kind','repository_identity','context_sha256',
            'bundle_digest','request_sha256','source_manifest_sha256',
            'validation_sha256','attempt','cases'}
            or oracle['schema_version'] != '1.0'
            or oracle['kind'] != 'native-prerequisite-postconditions-v1'
            or oracle['repository_identity'] != digest(str(root))
            or oracle['context_sha256'] != plan['binding']['context_sha256']
            or oracle['bundle_digest'] != approved_digest
            or oracle['validation_sha256'] != digest(validation_spec)
            or oracle['request_sha256'] != request_digest(spec)
            or oracle['source_manifest_sha256'] != digest(spec['files'])
            or type(oracle['attempt']) is not int or not 1 <= oracle['attempt'] <= 3
            or type(oracle['cases']) is not list
            or len(oracle['cases']) != len(spec['schedule'])
            or len(spec['schedule']) != len(validation_spec['cases'])
            or hashlib.sha256(canonical(oracle)).hexdigest() != trusted_oracle_sha256):
        raise InputError('Independent native prerequisite oracle differs from plan')
    try:
        inspect_receipt(spec, receipt, trusted_receipt_sha256=trusted_receipt_sha256)
    except RunnerError as error:
        raise InputError('Native prerequisite receipt invalid') from error
    if (receipt['scheduled'] != len(spec['schedule'])
            or receipt['recorded'] != receipt['scheduled']
            or receipt['exited_zero'] != receipt['scheduled']
            or not receipt['source_identity_valid']
            or set(outputs) != {case['case_id'] for case in spec['schedule']}):
        raise InputError('Native prerequisite schedule incomplete')
    for expected, reviewed, case, execution in zip(
            oracle['cases'], validation_spec['cases'], spec['schedule'], receipt['cases']):
        if (type(expected) is not dict or set(expected) != {'case_id','entry_sha256','observation'}
                or expected['case_id'] != case['case_id']
                or reviewed['case_id'] != case['case_id']
                or reviewed['entry'] != case['entry']
                or reviewed['entry_sha256'] != expected['entry_sha256']
                or reviewed['observation'] != expected['observation']
                or len([item for item in spec['files'] if item['path'] == case['entry']
                        and item['sha256'] == expected['entry_sha256']]) != 1
                or execution['outcome'] != 'exited_zero'
                or not execution['isolation_established']):
            raise InputError('Native prerequisite case binding or isolation failed')
        stdout, stderr = outputs[case['case_id']]
        if (hashlib.sha256(stdout).hexdigest() != execution['stdout_sha256']
                or hashlib.sha256(stderr).hexdigest() != execution['stderr_sha256']
                or stderr):
            raise InputError('Native prerequisite output differs from receipt')
        try:
            actual = _observation(stdout)
            wanted = _observation(canonical(expected['observation']) + b'\n')
        except RunnerError as error:
            raise InputError('Invalid native prerequisite observation') from error
        if actual != wanted:
            raise InputError('Independent native prerequisite postcondition failed')
    if prerequisite_status(root, recovery_bundle, approved_digest)['status'] != 'applied_requires_rescan':
        raise InputError('Prerequisite source changed during native inspection')
    return {'status':'validated_requires_rescan', 'scheduled':receipt['scheduled'],
            'recorded':receipt['recorded'], 'contract_digest':approved_digest,
            'trusted_receipt_sha256':trusted_receipt_sha256,
            'trusted_oracle_sha256':trusted_oracle_sha256,
            'recipe_applicable':False, 'integration_verified':False}
