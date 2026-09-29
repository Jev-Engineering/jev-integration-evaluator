"""One reviewed snapshot, one owned patch, and one recovery journal for a placement set.

This is a synthetic trusted-host path. It does not grant execution or deployment
authority and never relaxes the source checks of individual recipes.
"""
from __future__ import annotations

import ast
import hashlib
import math
import os
from pathlib import Path
import stat

from .. import __version__
from ..contracts import seal, verify, validate_contract, utc_now
from ..implementation import FORBIDDEN, apply_patch_plan, make_patch_plan, run_authorized_tests
from ..io import InputError, atomic_text, digest, file_hash, loads, read_json, safe_child, write_json
from .contracts import validate_inventory, validate_spec
from .lifecycle import (_bundle_dir, _root_identity, _write_bytes, _sync_dir, _lock,
                        _journal, _record, _inspect_file, engine_identity)
from .recipes import transform
from .verification import (_probe, _expected, _observable, _contract_assertions,
                           _pretty_size, MAX_RECEIPT_BYTES)
from .observations import validate_observation


def _selection(selection, specs):
    validate_contract(selection, 'composite-selection-v1')
    ids = selection['candidate_ids']
    if ids != sorted(set(ids)) or not 2 <= len(ids) <= 4 or set(specs) != set(ids):
        raise InputError('Composite selected set must contain two to four unique reviewed candidates')
    if len(selection['dependencies']) != len(set(tuple(x) for x in selection['dependencies'])):
        raise InputError('Duplicate composite dependency')
    if any(a not in ids or b not in ids or a == b for a,b in selection['dependencies']):
        raise InputError('Selected dependency graph is incomplete or cyclic')
    if any(a in ids and b in ids for a,b in selection['conflicts']):
        raise InputError('Selected candidates have an explicit conflict')
    remaining = set(ids)
    while remaining:
        ready = {item for item in remaining if all(a != item or b not in remaining
                 for a,b in selection['dependencies'])}
        if not ready: raise InputError('Selected dependency graph contains a cycle')
        remaining -= ready
    fields = ('task_field', 'policy_version', 'canary_scope')
    shared = selection['shared_runtime']
    if any(spec['runtime'].get(key) != shared.get(key) for spec in specs.values() for key in fields):
        raise InputError('Composite placements do not share task, policy and canary identity')
    if any(spec['runtime']['configuration'].get(key) != shared.get(key) for spec in specs.values()
           for key in ('max_calls_per_task','max_cost_per_task')):
        raise InputError('Composite placements do not share one call and cost budget')
    return digest(selection)


def _compose_file(root, rel, revisions):
    """Merge disjoint reviewed byte edits from the same original file."""
    path = safe_child(root, rel)
    old = path.read_bytes() if path.is_file() else b''
    if len(revisions) == 1: return revisions[0][1].decode('utf-8')
    if not path.is_file() or not rel.endswith('.py'):
        first = revisions[0][1]
        if all(content == first for _,content in revisions): return first.decode('utf-8')
        raise InputError('Conflicting composite output path: ' + rel)
    changes = []
    for candidate, content in revisions:
        try:
            individual = ast.parse(content.decode('utf-8'), filename=rel)
        except (SyntaxError,UnicodeError):
            raise InputError('Invalid independent candidate edit in ' + rel + ': ' + candidate) from None
        generated = [node for node in individual.body if isinstance(node,ast.ImportFrom)
                     and any(alias.asname and alias.asname.startswith('_jev_invoke_')
                             for alias in node.names)]
        if len(generated) != 1:
            raise InputError('Candidate adapter import is ambiguous in ' + rel + ': ' + candidate)
        lines = content.splitlines(keepends=True)
        line = generated[0].lineno - 1
        start = sum(map(len,lines[:line])); inserted = lines[line]
        if (not inserted.endswith((b'\n',b'\r\n')) or
                not inserted.lstrip().startswith(b'from ')):
            raise InputError('Candidate adapter import is not a complete statement in ' + rel + ': ' + candidate)
        without_import = content[:start] + content[start+len(inserted):]
        # The import is inserted before the selected call. Its preceding bytes
        # must still be the original source prefix, preventing a shifted anchor.
        if old[:start] != content[:start]:
            raise InputError('Candidate adapter import moved across changed source in ' + rel + ': ' + candidate)
        changes.append((start,start,inserted,candidate))
        previous = ast.parse(old.decode('utf-8'),filename=rel)
        after = ast.parse(without_import.decode('utf-8'),filename=rel)
        if len(previous.body) != len(after.body):
            raise InputError('Unsupported same-file candidate change in ' + rel + ': ' + candidate)
        different = [(before,now) for before,now in zip(previous.body,after.body)
                     if ast.dump(before,include_attributes=False) != ast.dump(now,include_attributes=False)]
        if (len(different) != 1 or not all(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
                                          for node in different[0])
                or different[0][0].name != different[0][1].name):
            raise InputError('Unsupported same-file candidate change in ' + rel + ': ' + candidate)
        before,now = different[0]
        old_lines = old.splitlines(keepends=True)
        new_lines = without_import.splitlines(keepends=True)
        old_start = sum(map(len,old_lines[:before.lineno-1]))
        old_end = sum(map(len,old_lines[:before.end_lineno]))
        new_start = sum(map(len,new_lines[:now.lineno-1]))
        new_end = sum(map(len,new_lines[:now.end_lineno]))
        if old[:old_start] != without_import[:new_start] or old[old_end:] != without_import[new_end:]:
            raise InputError('Unsupported same-file candidate change in ' + rel + ': ' + candidate)
        changes.append((old_start,old_end,without_import[new_start:new_end],candidate))
    # Insertion at one byte offset is compatible only for unique complete import
    # statements. Other shared offsets and all overlapping spans are rejected.
    grouped = {}
    for start,end,replacement,candidate in changes:
        grouped.setdefault((start,end), []).append((candidate,replacement))
    combined = []
    for (start,end), rows in grouped.items():
        if len(rows) == 1:
            combined.append((start,end,rows[0][1],rows[0][0]))
            continue
        def one_static_import(item):
            try:
                parsed = ast.parse(item.decode('utf-8'))
            except (SyntaxError, UnicodeError):
                return False
            return (item.endswith((b'\n',b'\r\n')) and len(parsed.body) == 1
                    and isinstance(parsed.body[0],(ast.Import,ast.ImportFrom))
                    and not any(isinstance(alias,ast.alias) and alias.name == '*'
                                for alias in parsed.body[0].names))
        if start != end or any(not one_static_import(item) for _,item in rows):
            raise InputError('Overlapping candidate edits in ' + rel + ': ' + ','.join(sorted(x for x,_ in rows)))
        statements = sorted(set(item for _,item in rows))
        combined.append((start,end,b''.join(statements),','.join(sorted(x for x,_ in rows))))
    combined.sort(key=lambda row: (row[0],row[1],row[3]))
    for left,right in zip(combined,combined[1:]):
        if left[1] > right[0]:
            raise InputError('Overlapping candidate edits in ' + rel + ': ' + left[3] + ',' + right[3])
    result = bytearray(old)
    for start,end,replacement,_ in reversed(combined):
        result[start:end] = replacement
    try:
        text = result.decode('utf-8')
        tree = ast.parse(text, filename=rel)
    except (SyntaxError, UnicodeError):
        raise InputError('Composite edits do not form valid UTF-8 Python: ' + rel) from None
    # Each independent generated alias must survive the composition exactly once.
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    for candidate, content in revisions:
        individual = ast.parse(content.decode('utf-8'), filename=rel)
        aliases = {alias.asname for node in individual.body if isinstance(node, ast.ImportFrom)
                   for alias in node.names if alias.asname and alias.asname.startswith('_jev_invoke_')}
        if not aliases or any(sum(alias.asname == name for node in imports
                              for alias in node.names) != 1 for name in aliases):
            raise InputError('Composite lost or duplicated selected adapter import: ' + candidate)
    return text


def plan_composite(root, inventory, selection, specs, output):
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(output)
    if bundle.is_relative_to(root) or bundle == root or (bundle.exists() and any(bundle.iterdir())):
        raise InputError('Composite output must be a new private directory outside the target')
    if type(specs) is not dict: raise InputError('Composite specifications must be keyed by candidate')
    checked = {key:validate_spec(value) for key,value in specs.items()}
    selected_digest = _selection(selection, checked)
    snapshot = digest(inventory)
    revisions = {}
    derived = {}
    discovery = {}
    for candidate in selection['candidate_ids']:
        spec = checked[candidate]
        if spec['candidate_id'] != candidate or spec['inventory_sha256'] != snapshot:
            raise InputError('Composite candidate or inventory differs from the reviewed snapshot')
        validate_inventory(root, inventory, spec)
        derived[candidate] = transform(root, spec)
        for change in derived[candidate]['changes']:
            rel = change['file']
            if FORBIDDEN.search(rel): raise InputError('Protected composite output')
            revisions.setdefault(rel, []).append((candidate,change['new_content'].encode('utf-8')))
        for rel, expected in derived[candidate].get('contributing_sources',{}).items():
            if rel in discovery and discovery[rel]['sha256'] != expected:
                raise InputError('Conflicting contributed source identity')
            discovery[rel] = {'sha256':expected,'mode':stat.S_IMODE(safe_child(root,rel).stat().st_mode)}
    for row in inventory['files'] + inventory.get('configuration_evidence',[]):
        path = safe_child(root,row['file'])
        value = {'sha256':row['sha256'],'mode':stat.S_IMODE(path.stat().st_mode)}
        if row['file'] in discovery and discovery[row['file']] != value:
            raise InputError('Composite source scope conflicts with reviewed inventory')
        discovery[row['file']] = value
    console_report = None
    if any('entrypoint_binding' in spec for spec in checked.values()):
        from .composite_console import render_composite_console
        console_text, console_report = render_composite_console(root, selection, checked)
        rel = console_report['file']
        if set(candidate for candidate, _ in revisions.get(rel, [])) != set(selection['candidate_ids']):
            raise InputError('Composite console ownership differs from selected placements')
        revisions[rel] = [(selection['candidate_ids'][0], console_text.encode('utf-8'))]
    changes = [{'file':rel,'new_content':_compose_file(root,rel,items)} for rel,items in sorted(revisions.items())]
    patch = make_patch_plan(root, changes, selection['candidate_ids'])
    if any(stat.S_IMODE(safe_child(root,row['file']).stat().st_mode) & 0o7000
           for row in patch['changes'] if safe_child(root,row['file']).exists()):
        raise InputError('Privileged source file mode is unsupported')
    bundle.mkdir(parents=True); os.chmod(bundle,0o700)
    owned = []
    for change in patch['changes']:
        path = safe_child(root,change['file'])
        old_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        preimage = 'preimages/' + digest(change['file']) + '.utf8' if path.exists() else None
        if preimage: _write_bytes(safe_child(bundle,preimage),path.read_bytes())
        owned.append({'file':change['file'],'old_sha256':change['old_sha256'],
                      'new_sha256':change['new_sha256'],'old_mode':old_mode,
                      'new_mode':old_mode if old_mode is not None else (0o666 if os.name == 'nt' else 0o600),
                      'preimage':preimage})
    artifacts = {'selection.json':selection,'reviewed-inventory.json':inventory,
                 'specifications.json':checked,'patch-plan.json':patch,
                 'derived-manifests.json':{key:{k:v for k,v in value.items() if k!='changes'}
                                           for key,value in derived.items()}}
    if console_report is not None:
        artifacts['composite-console.json'] = console_report
    for name,value in artifacts.items(): write_json(bundle/name,value)
    hashes = {name:file_hash(bundle/name) for name in artifacts}
    hashes.update({row['preimage']:file_hash(safe_child(bundle,row['preimage']))
                   for row in owned if row['preimage']})
    plan = seal({'schema_version':'composite-implementation-v1','root_identity':_root_identity(root),
                 'engine_version':__version__,'engine_identity':engine_identity(),
                 'selected_set_digest':selected_digest,'inventory_sha256':snapshot,
                 'specs_sha256':digest(checked),'patch_digest':patch['plan_digest'],
                 'candidate_ids':selection['candidate_ids'],'owned_files':owned,
                 'discovery_files':discovery,'artifacts':hashes})
    validate_contract(plan,'composite-plan-v1')
    write_json(bundle/'composite-plan.json',plan); _sync_dir(bundle)
    _record(bundle,plan,'planned')
    return {'status':'planned','bundle_digest':plan['contract_digest'],
            'selected_set_digest':selected_digest,'target_modified':False,'target_executed':False,
            'owned_files':len(owned)}


def _load(root, bundle, *, current_engine=False):
    root, bundle = Path(root).resolve(strict=True), _bundle_dir(bundle)
    if bundle.is_relative_to(root): raise InputError('Composite bundle must remain outside target')
    plan = read_json(safe_child(bundle,'composite-plan.json'))
    validate_contract(plan,'composite-plan-v1'); verify(plan)
    if plan['root_identity'] != _root_identity(root): raise InputError('Wrong composite target worktree')
    if current_engine and plan['engine_identity'] != engine_identity():
        raise InputError('Composite engine changed; replan and review')
    expected = {'selection.json','reviewed-inventory.json','specifications.json',
                'patch-plan.json','derived-manifests.json'}
    if 'composite-console.json' in plan['artifacts']:
        expected.add('composite-console.json')
    expected.update(row['preimage'] for row in plan['owned_files'] if row['preimage'])
    if set(plan['artifacts']) != expected:
        raise InputError('Composite artifact set differs from reviewed plan')
    for rel,sha in plan['artifacts'].items():
        path = safe_child(bundle,rel)
        if not path.is_file() or file_hash(path) != sha:
            raise InputError('Composite artifact integrity mismatch')
    selection = read_json(bundle/'selection.json')
    inventory = read_json(bundle/'reviewed-inventory.json')
    specs = read_json(bundle/'specifications.json')
    patch = read_json(bundle/'patch-plan.json')
    validate_contract(patch,'patch-plan')
    verify(patch,'plan_digest')
    if (_selection(selection,specs) != plan['selected_set_digest'] or
            digest(inventory) != plan['inventory_sha256'] or
            digest(specs) != plan['specs_sha256'] or
            patch['plan_digest'] != plan['patch_digest'] or
            patch['candidate_ids'] != plan['candidate_ids'] or
            patch['repository_identity'] != digest(str(root))):
        raise InputError('Composite selected set, source or patch identity changed')
    if any('entrypoint_binding' in spec for spec in specs.values()):
        if 'composite-console.json' not in plan['artifacts']:
            raise InputError('Composite console binding report missing')
        report = read_json(bundle/'composite-console.json')
        edits = [row for row in patch['changes'] if row['file'] == report.get('file')]
        if (report.get('candidate_ids') != plan['candidate_ids'] or
                report.get('selected_set_digest') != plan['selected_set_digest'] or
                len(edits) != 1 or report.get('file_sha256') != edits[0]['new_sha256']):
            raise InputError('Composite console binding differs from reviewed patch')
    elif 'composite-console.json' in plan['artifacts']:
        raise InputError('Unreviewed composite console report')
    for cid,spec in specs.items():
        validate_spec(spec)
        if cid != spec['candidate_id'] or spec['inventory_sha256'] != plan['inventory_sha256']:
            raise InputError('Composite member provenance mismatch')
    owned = {row['file']:row for row in plan['owned_files']}
    permitted = set().union(*(set(spec['output']['permitted_edits']) for spec in specs.values()))
    if (len(owned) != len(plan['owned_files']) or set(owned) != permitted
            or {row['file'] for row in patch['changes']} != set(owned)):
        raise InputError('Composite patch ownership differs from reviewed plan')
    if len(patch['changes']) != len(owned): raise InputError('Duplicate composite patch path')
    for change in patch['changes']:
        row = owned[change['file']]
        if (FORBIDDEN.search(change['file']) or change['old_sha256'] != row['old_sha256']
                or change['new_sha256'] != row['new_sha256']
                or (row['preimage'] is not None and row['old_mode'] != row['new_mode'])
                or hashlib.sha256(change['new_content'].encode('utf-8')).hexdigest() != row['new_sha256']
                or (row['preimage'] is not None and
                    file_hash(safe_child(bundle,row['preimage'])) != row['old_sha256'])):
            raise InputError('Composite owned content differs from reviewed plan')
    _journal(bundle,plan)
    return root,bundle,plan,selection,inventory,specs,patch


def _check_discovery(root,plan,*,applied=False):
    owned = {row['file']:row for row in plan['owned_files']}
    for rel,row in plan['discovery_files'].items():
        path = safe_child(root,rel)
        expected = owned[rel]['new_sha256'] if applied and rel in owned else row['sha256']
        if not path.is_file() or file_hash(path) != expected or stat.S_IMODE(path.stat().st_mode) != row['mode']:
            raise InputError('Composite reviewed source or mode drift')


def _generation(bundle,plan,events):
    for row in reversed(_journal(bundle,plan)):
        if row['event'] in events:
            return row['contract_digest']
    raise InputError('Composite transaction generation is missing')


def _receipt(bundle,plan,phase, trusted_sha256=None, specs=None):
    name = 'baseline-receipt.json' if phase == 'baseline' else 'verification-receipt.json'
    path = safe_child(bundle,name)
    if not path.is_file() or (trusted_sha256 is not None and file_hash(path) != trusted_sha256):
        raise InputError('Missing or unanchored composite ' + phase + ' receipt')
    receipt = read_json(path)
    validate_contract(receipt,'composite-receipt-v1'); verify(receipt)
    if (receipt['bundle_digest'] != plan['contract_digest'] or
            receipt['selected_set_digest'] != plan['selected_set_digest'] or
            receipt['engine_identity'] != plan['engine_identity'] or
            receipt['phase'] != phase or
            receipt['file_hashes'] != {row['file']:row['old_sha256' if phase=='baseline' else 'new_sha256']
                                       for row in plan['owned_files']}):
        raise InputError('Composite execution receipt context mismatch')
    if specs is not None:
        expected = [(cid,case['id'],mode) for cid in plan['candidate_ids']
                    for case in specs[cid]['verification']['cases']
                    for mode in (('baseline',) if phase == 'baseline' else ('off','shadow','active'))]
        rows = receipt['results']
        if ([(row['candidate_id'],row['case_id'],row['mode']) for row in rows] != expected
                or receipt['scheduled_cases'] != len(expected)
                or receipt['completed_cases'] != sum(row['status'] in ('passed','failed') for row in rows)):
            raise InputError('Composite receipt omits or reorders scheduled cases')
        for row in rows:
            if row['observation'] is not None:
                validate_observation(row['observation'],specs[row['candidate_id']])
            elif row['status'] == 'passed':
                raise InputError('Passing composite row lacks an observed host result')
        check = receipt['combined_check']
        commands = [(cid,digest(specs[cid]['verification'][phase+'_command']))
                    for cid in plan['candidate_ids'] if specs[cid]['verification'][phase+'_command']]
        if [(row['candidate_id'],row['command_sha256']) for row in receipt['member_commands']] != commands:
            raise InputError('Composite receipt omits a member verification command')
        if phase == 'baseline' and (check is not None or receipt['baseline_receipt_sha256'] is not None):
            raise InputError('Baseline composite receipt has modified-only evidence')
        if phase == 'modified' and (check is None or
                check['command_sha256'] != digest(read_json(bundle/'selection.json')['combined_verification']['command'])):
            raise InputError('Composite shared verification command changed')
        if receipt['status'] == 'passed' and (any(row['status'] != 'passed' for row in rows)
                or any(row['status'] != 'passed' for row in receipt['member_commands'])
                or (phase == 'modified' and (check['status'] != 'passed' or not check['shared_budget_valid']))):
            raise InputError('Passing composite receipt contradicts scheduled failures')
    return receipt


def status_composite(root,bundle,*,trusted_receipt_sha256=None):
    root,bundle,plan,_,_,specs,_ = _load(root,bundle)
    identities = {row['file']:_inspect_file(root,row) for row in plan['owned_files']}
    states = set(identities.values())
    events = [row['event'] for row in _journal(bundle,plan)]
    terminal = {'planned','applied_unverified','verified','verification_failed','rolled_back',
                'baseline_verification_passed','baseline_verification_failed'}
    if states == {'baseline'}:
        state = 'rolled_back' if events and events[-1] == 'rolled_back' else 'planned'
    elif states == {'applied'}: state = 'applied_unverified'
    else: state = 'blocked_recovery'
    if events and events[-1] not in terminal: state = 'blocked_recovery'
    trust = 'absent'
    if (bundle/'verification-receipt.json').is_file():
        receipt = _receipt(bundle,plan,'modified',trusted_receipt_sha256,specs)
        current_generation = _generation(bundle,plan,{'applied_unverified'}) if 'applied_unverified' in events else None
        fresh = receipt['generation_sha256'] == current_generation
        trust = 'integrity_consistent_but_unverified' if fresh else 'stale_generation'
        if fresh and state == 'applied_unverified' and receipt['status'] == 'failed':
            state = 'verification_failed'
        if fresh and state == 'applied_unverified' and trusted_receipt_sha256 is not None and receipt['status'] == 'passed':
            _check_discovery(root,plan,applied=True)
            if plan['engine_identity'] != engine_identity():
                raise InputError('Composite receipt refers to changed engine')
            state,trust = 'verified','externally_anchored_execution'
    return {'status':state,'bundle_digest':plan['contract_digest'],
            'selected_set_digest':plan['selected_set_digest'],'file_identity':identities,
            'receipt_trust':trust,'rollback_digest':rollback_digest(plan),
            'target_executed':False,'runtime_activation_authorized':False}


def apply_composite(root,bundle,approval,*,baseline_sha256):
    root,bundle,plan,selection,inventory,specs,patch = _load(root,bundle,current_engine=True)
    if approval != plan['contract_digest'] or not baseline_sha256:
        raise InputError('Exact composite approval and external baseline receipt are required')
    with _lock(bundle,root):
        receipt = _receipt(bundle,plan,'baseline',baseline_sha256,specs)
        if (receipt['status'] != 'passed' or receipt['generation_sha256'] !=
                _generation(bundle,plan,{'planned','rolled_back'})):
            raise InputError('Composite baseline failed or belongs to an earlier generation')
        current = status_composite(root,bundle)
        if current['status'] in ('applied_unverified','verification_failed'):
            _check_discovery(root,plan,applied=True)
            return {**current,'idempotent':True}
        if current['status'] != 'planned':
            raise InputError('Composite transaction needs explicit recovery')
        reproduced = {}
        for cid in selection['candidate_ids']:
            validate_inventory(root,inventory,specs[cid])
            for change in transform(root,specs[cid])['changes']:
                reproduced.setdefault(change['file'],[]).append((cid,change['new_content'].encode('utf-8')))
        if 'composite-console.json' in plan['artifacts']:
            from .composite_console import render_composite_console
            console_text, report = render_composite_console(root, selection, specs)
            if report != read_json(bundle/'composite-console.json'):
                raise InputError('Composite console source binding changed before apply')
            reproduced[report['file']] = [(selection['candidate_ids'][0], console_text.encode('utf-8'))]
        expected = {rel:_compose_file(root,rel,items) for rel,items in reproduced.items()}
        if expected != {row['file']:row['new_content'] for row in patch['changes']}:
            raise InputError('Composite patch differs from independently reproduced recipes')
        _check_discovery(root,plan)
        if any(_inspect_file(root,row) != 'baseline' for row in plan['owned_files']):
            raise InputError('Composite owned path drift before apply')
        _record(bundle,plan,'apply_started')
        def progress(event,change):
            if event == 'write_completed': _sync_dir(safe_child(root,change['file']).parent)
            _record(bundle,plan,'apply_'+event,change['file'])
        try:
            apply_patch_plan(root,patch,patch['plan_digest'],progress=progress)
        except Exception:
            _record(bundle,plan,'apply_failed_recovery_required')
            raise
        if any(_inspect_file(root,row) != 'applied' for row in plan['owned_files']):
            _record(bundle,plan,'apply_identity_failed')
            raise InputError('Composite applied bytes/modes differ')
        _record(bundle,plan,'applied_unverified')
        return status_composite(root,bundle)


def rollback_digest(plan):
    return digest({'operation':'restore_composite_owned_preimages',
                   'bundle_digest':plan['contract_digest'],
                   'selected_set_digest':plan['selected_set_digest'],
                   'owned_files':plan['owned_files']})


def rollback_composite(root,bundle,approval):
    root,bundle,plan,_,_,_,_ = _load(root,bundle)
    if approval != rollback_digest(plan): raise InputError('Exact composite rollback approval required')
    with _lock(bundle,root):
        identities = {row['file']:_inspect_file(root,row) for row in plan['owned_files']}
        if 'drift' in identities.values():
            raise InputError('Concurrent owned-byte change; composite rollback refuses overwrite')
        if set(identities.values()) == {'baseline'}:
            _record(bundle,plan,'rolled_back')
            return {'status':'rolled_back','idempotent':True}
        _record(bundle,plan,'rollback_started')
        for row in reversed(plan['owned_files']):
            if identities[row['file']] != 'applied': continue
            path = safe_child(root,row['file'])
            if _inspect_file(root,row) != 'applied':
                raise InputError('Composite owned byte changed during rollback')
            _record(bundle,plan,'rollback_write_started',row['file'])
            if row['preimage'] is None:
                path.unlink(); _sync_dir(path.parent)
            else:
                # The applied file already has the reviewed original mode. The
                # atomic writer copies that mode onto its temp file before one
                # replace, so a crash exposes either recognized byte/mode pair.
                atomic_text(path,safe_child(bundle,row['preimage']).read_bytes().decode('utf-8'))
                _sync_dir(path.parent)
            _record(bundle,plan,'rollback_write_completed',row['file'])
        if any(_inspect_file(root,row) != 'baseline' for row in plan['owned_files']):
            raise InputError('Composite rollback incomplete; retain recovery bundle')
        _record(bundle,plan,'rolled_back')
        return {'status':'rolled_back','owned_changes_restored':len(plan['owned_files']),
                'unrelated_paths_modified':False}


def _combined_check(root,selection):
    declaration = selection['combined_verification']
    command = declaration['command']
    try:
        execution = run_authorized_tests(root,command,approve_execution=True,timeout_s=120)
    except OSError:
        execution = {'status':'not_run','stdout':''}
    stdout = execution['stdout']
    valid = False
    if execution['status'] == 'passed':
        try:
            observed = loads(stdout)
            ids = selection['candidate_ids']
            tokens = observed['coordinator_tokens']
            scopes = observed['canary_scopes']
            calls = observed['assessment_calls']
            cost = observed['total_cost']
            valid = (type(observed) is dict and set(observed) == {
                'schema_version','candidate_ids','task_id','coordinator_tokens',
                'canary_scopes','assessment_calls','total_cost','audit_candidate_ids','results'}
                and observed['schema_version'] == 'composite-host-observation-v1'
                and observed['candidate_ids'] == ids and observed['audit_candidate_ids'] == ids
                and observed['task_id'] == declaration['shared_task_id']
                and type(tokens) is list and len(tokens) == len(ids)
                and all(type(x) is str and x for x in tokens) and len(set(tokens)) == 1
                and scopes == [selection['shared_runtime']['canary_scope']]*len(ids)
                and type(calls) is int and 1 <= calls <= selection['shared_runtime']['max_calls_per_task']
                and type(cost) in (int,float) and math.isfinite(cost)
                and 0 <= cost <= selection['shared_runtime']['max_cost_per_task']
                and observed['results'] == declaration['expected_results']
                and set(observed['results']) == set(ids))
        except (ValueError, TypeError, KeyError, OverflowError):
            valid = False
    return {'command_sha256':digest(command),
            'stdout_sha256':hashlib.sha256(stdout.encode('utf-8')).hexdigest(),
            'status':execution['status'],'shared_budget_valid':valid}


def _bounded_receipt(body):
    """Keep every scheduled row while failing oversized private observations."""
    body['contract_digest'] = '0'*64
    if _pretty_size(body)+1 > MAX_RECEIPT_BYTES:
        body['status'] = 'failed'
        for row in reversed(body['results']):
            if row['observation'] is None: continue
            row.update(status='failed',observation=None,assertions=[])
            if _pretty_size(body)+1 <= MAX_RECEIPT_BYTES: break
    if _pretty_size(body)+1 > MAX_RECEIPT_BYTES:
        raise InputError('Composite receipt metadata exceeds bounded reader')
    del body['contract_digest']
    return seal(body)


def verify_composite(root,bundle,phase,*,approve_execution=False,baseline_sha256=None):
    if approve_execution is not True:
        raise InputError('Composite host execution requires separate explicit authority')
    if phase not in ('baseline','modified'):
        raise InputError('Composite phase must be baseline or modified')
    root,bundle,plan,selection,_,specs,_ = _load(root,bundle,current_engine=True)
    with _lock(bundle,root):
        state = 'baseline' if phase == 'baseline' else 'applied'
        if any(_inspect_file(root,row) != state for row in plan['owned_files']):
            raise InputError('Composite files differ from requested verification phase')
        _check_discovery(root,plan,applied=phase=='modified')
        baseline_rows = {}
        if phase == 'modified':
            if not baseline_sha256:
                raise InputError('External composite baseline receipt digest required')
            baseline = _receipt(bundle,plan,'baseline',baseline_sha256,specs)
            if (baseline['status'] != 'passed' or baseline['generation_sha256'] !=
                    _generation(bundle,plan,{'planned','rolled_back'})):
                raise InputError('Composite baseline failed or belongs to an earlier generation')
            baseline_rows = {(row['candidate_id'],row['case_id']):row
                             for row in baseline['results']}
        _record(bundle,plan,'baseline_verification_started' if phase=='baseline'
                else 'verification_started')
        results = []
        for cid in plan['candidate_ids']:
            spec = specs[cid]
            for case in spec['verification']['cases']:
                for mode in (('baseline',) if phase=='baseline' else ('off','shadow','active')):
                    observation,execution_status = None,'failed'
                    try:
                        observation,execution_status = _probe(root,bundle,plan,spec,case,mode)
                        if execution_status == 'passed': validate_observation(observation,spec)
                        else: observation = None
                    except (InputError, ValueError,TypeError,OSError,RecursionError):
                        observation,execution_status = None,'failed'
                    assertions = []
                    if observation is not None:
                        assertions = _expected(observation,case['active'] if mode=='active' else case['baseline'])
                        passed = len(assertions) == 4
                        if mode != 'baseline':
                            reached = (observation['adapter_calls'] > 0 and
                                       observation['adapter_calls'] == observation['calls'].get(spec['source']['symbol'],0))
                            if reached: assertions.append('selected_adapter_reached')
                            else: passed = False
                        if mode in ('off','shadow'):
                            old = baseline_rows[(cid,case['id'])]['observation']
                            if _observable(observation,spec) == _observable(old,spec):
                                assertions.append('baseline_parity')
                            else: passed = False
                            if mode == 'off' and observation['model_calls'] != 0: passed = False
                        if observation['trace_truncated'] or observation['network_attempts_denied']:
                            passed = False
                        execution_status = 'passed' if passed else 'failed'
                    results.append({'candidate_id':cid,'case_id':case['id'],'mode':mode,
                                    'status':execution_status,'observation':observation,
                                    'assertions':assertions})
        member_commands = []
        for cid in plan['candidate_ids']:
            command = specs[cid]['verification'][phase+'_command']
            if not command: continue
            try:
                check = run_authorized_tests(root,command,approve_execution=True,
                    timeout_s=specs[cid]['verification']['timeout_s'])
                command_status = check['status']
            except OSError: command_status = 'not_run'
            member_commands.append({'candidate_id':cid,'command_sha256':digest(command),
                                    'status':command_status})
        combined = _combined_check(root,selection) if phase == 'modified' else None
        contracts_pass = True
        if phase == 'modified':
            for cid in plan['candidate_ids']:
                member = [row for row in results if row['candidate_id'] == cid]
                old = {case:row for (candidate,case),row in baseline_rows.items() if candidate==cid}
                contracts_pass = contracts_pass and len(_contract_assertions(member,specs[cid],old)) == 4
        try:
            _check_discovery(root,plan,applied=phase=='modified')
            file_valid = all(_inspect_file(root,row)==state for row in plan['owned_files'])
        except (InputError,OSError): file_valid = False
        passed = (file_valid and contracts_pass and all(row['status']=='passed' for row in results)
                  and all(row['status']=='passed' for row in member_commands)
                  and (combined is None or (combined['status']=='passed' and combined['shared_budget_valid'])))
        receipt = _bounded_receipt({'schema_version':'composite-receipt-v1','bundle_digest':plan['contract_digest'],
                        'selected_set_digest':plan['selected_set_digest'],
                        'engine_identity':plan['engine_identity'],'phase':phase,
                        'generation_sha256':_generation(bundle,plan,
                            {'planned','rolled_back'} if phase=='baseline' else {'applied_unverified'}),
                        'status':'passed' if passed else 'failed',
                        'file_hashes':{row['file']:row['old_sha256' if phase=='baseline' else 'new_sha256']
                                       for row in plan['owned_files']},
                        'scheduled_cases':len(results),
                        'completed_cases':sum(row['status'] in ('passed','failed') for row in results),
                        'results':results,'member_commands':member_commands,'combined_check':combined,
                        'baseline_receipt_sha256':baseline_sha256 if phase=='modified' else None,
                        'classification':'synthetic','activation_authorized':False})
        passed = receipt['status'] == 'passed'
        validate_contract(receipt,'composite-receipt-v1')
        name = 'baseline-receipt.json' if phase=='baseline' else 'verification-receipt.json'
        write_json(bundle/name,receipt); _sync_dir(bundle)
        _record(bundle,plan,('baseline_verification_passed' if passed else 'baseline_verification_failed')
                if phase=='baseline' else ('verified' if passed else 'verification_failed'))
        return {'status':('baseline_passed' if phase=='baseline' else 'verified') if passed
                else 'verification_failed','receipt_sha256':file_hash(bundle/name),
                'bundle_digest':plan['contract_digest'],'selected_set_digest':plan['selected_set_digest'],
                'scheduled_cases':len(results),
                'passed_cases':sum(row['status']=='passed' for row in results),
                'classification':'synthetic','runtime_activation_authorized':False}
