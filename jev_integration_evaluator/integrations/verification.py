"""Tool-owned assertions over isolated, byte-matched host executions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import platform
import shutil
import stat
import sys
import tempfile

from ..contracts import seal, utc_now, validate_contract
from ..implementation import run_authorized_tests
from ..io import InputError, digest, file_hash, read_json, safe_child, write_json
from .lifecycle import (_load, _lock, _check_discovery, _inspect_file, _receipt, _record,
                        implementation_status)
from .recipes import RECIPES
from .observations import validate_observation


# Match the bounded reader used by lifecycle receipt loading.
MAX_RECEIPT_BYTES = 64_000_000


def _pretty_size(value, continuation_indent=0):
    """Count write_json's UTF-8/indentation format without a full output buffer."""
    encoder = json.JSONEncoder(indent=2, ensure_ascii=False, allow_nan=False)
    return sum(len(part.encode('utf-8')) + part.count('\n')*continuation_indent
               for part in encoder.iterencode(value))


def _bounded_receipt(receipt):
    # A real digest has this fixed width. Include it and write_json's newline in
    # the budget before sealing, so every emitted receipt can be read back.
    receipt['contract_digest'] = '0'*64
    size = _pretty_size(receipt) + 1
    if size > MAX_RECEIPT_BYTES:
        size += _pretty_size('failed') - _pretty_size(receipt['status'])
        size += _pretty_size([], 2) - _pretty_size(receipt['contract_assertions'], 2)
        receipt['status'], receipt['contract_assertions'] = 'failed', []
        for row in reversed(receipt['results']):
            if row['observation'] is None:
                continue
            # A result object is indented four spaces inside the receipt.
            # Subtract its exact old contribution; avoid reserializing the whole
            # potentially large receipt for every discarded observation.
            previous = _pretty_size(row, 4)
            row.update(status='failed', observation=None, assertions=[], diagnostic='receipt_size_limit')
            size += _pretty_size(row, 4) - previous
            if size <= MAX_RECEIPT_BYTES:
                break
    # Bounded schedule metadata fits the reader independently of observations.
    # Keep a final exact check as a guard if that contract is expanded later.
    if size > MAX_RECEIPT_BYTES or _pretty_size(receipt) + 1 > MAX_RECEIPT_BYTES:
        raise InputError('Implementation receipt metadata exceeds the local byte limit')
    return seal(receipt)


def _lookup(data, path):
    for key in path.split('.'):
        if not isinstance(data, dict) or key not in data: return object()
        data = data[key]
    return data


def _expected(observation, expected):
    checks = []
    if observation['outcome']['result'] == expected['result']: checks.append('declared_result')
    if observation['outcome']['exception'] == expected['exception']: checks.append('declared_exception')
    if all(observation['calls'].get(k, 0) == v for k,v in expected['calls'].items()): checks.append('declared_call_counts')
    if all(_lookup(observation['globals'], k) == v for k,v in expected['globals'].items()): checks.append('declared_global_state')
    return checks


def _effects(observation, spec):
    return {name:observation['calls'].get(name,0) for name in spec['verification']['effect_symbols']}


def _observable(observation, spec):
    return {'outcome':observation['outcome'],'globals':observation['globals'],'effects':_effects(observation,spec)}


def _probe(root, bundle, plan, spec, case, mode):
    """Each case gets fresh copied source; nothing is executed in the planned target."""
    with tempfile.TemporaryDirectory(prefix='.host-probe-', dir=bundle) as scratch:
        scratch = Path(scratch)
        work = scratch / 'target'; work.mkdir()
        identities = {rel: (row['sha256'], row['mode']) for rel, row in plan['discovery_files'].items()}
        phase = 'old' if mode == 'baseline' else 'new'
        identities.update({row['file']: (row[phase+'_sha256'], row[phase+'_mode'])
                           for row in plan['owned_files']})
        total = 0
        for rel, (expected_hash, expected_mode) in sorted(identities.items()):
            source = safe_child(root, rel)
            if expected_hash is None:
                if source.exists(): raise InputError('Reserved output appeared during baseline source copy')
                continue
            if not source.is_file() or stat.S_IMODE(source.stat().st_mode) != expected_mode:
                raise InputError('Reviewed source or file mode changed before isolated copy')
            total += source.stat().st_size
            if total > 128_000_000: raise InputError('Isolated probe source-copy limit exceeded')
            dest = safe_child(work, rel); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest); dest.chmod(expected_mode)
            # Comparing the copy only with the current source would accept a
            # consistently changed but unreviewed snapshot after phase preflight.
            if file_hash(dest) != expected_hash:
                raise InputError('Isolated probe copy differs from the reviewed phase hash')
        request, output = scratch / 'request.json', scratch / 'result.json'
        write_json(request, {'root':str(work),'spec':spec,'case':case,'mode':mode,
                             'contributing_sources':{rel:row['sha256'] for rel,row in plan['discovery_files'].items()
                                                     if rel.endswith('.py')}})
        trusted_root = str(Path(__file__).resolve().parents[2])
        bootstrap = 'import sys;sys.path.insert(0,' + repr(trusted_root) + ');from jev_integration_evaluator.integrations.probe import main;main()'
        command = [sys.executable,'-I','-c',bootstrap,str(request),str(output)]
        run = run_authorized_tests(work, command, approve_execution=True, timeout_s=spec['verification']['timeout_s'])
        if run['status'] != 'passed' or not output.is_file() or output.stat().st_size > 2_000_000:
            return None, run['status'] if run['status'] != 'passed' else 'failed'
        return read_json(output), 'passed'


def _events(observation, role, event):
    return [row for row in observation['trace'] if row['role']==role and row['event']==event]


def _contract_assertions(results, spec, baseline_results):
    """These predicates are code-owned; an asserted manifest status is never used."""
    active = [r['observation'] for r in results if r['mode']=='active' and r['status']=='passed']
    checks = []
    if not active: return checks
    pattern = spec['recipe']['id'].split('.')[-1]
    if all(o['handler_calls'] >= 1 for o in active): checks.append('pattern_specific_handler_observed')
    changed = any(_observable(r['observation'], spec) != _observable(baseline_results[r['case_id']]['observation'], spec)
                  and r['observation']['model_calls'] >= 1 for r in results if r['mode']=='active' and r['status']=='passed')
    if changed: checks.append('assessment_changes_finite_host_behavior')
    if all(not o['trace_truncated'] and o['network_attempts_denied']==0 for o in active):
        checks.append('complete_offline_observation')
    ok = False
    if pattern in ('A','B','C','I','J','L'):
        ok = all(sum(_effects(o,spec).values()) <= 1 for o in active)
        if pattern in ('A','B','L'):
            ok = ok and any(o['calls'].get(spec['bindings']['blocked'],0)>0 and sum(_effects(o,spec).values())==0 for o in active)
        if pattern == 'B': ok = ok and any(_events(o,'risk','return') for o in active)
        if pattern == 'I': ok = ok and any(_events(o,'reserve_retry','return') or o['calls'].get(spec['bindings']['completed'],0) for o in active)
        if pattern == 'J': ok = ok and any(_events(o,'verify_child','return') and _events(o,'finish','call') for o in active)
        if pattern == 'L': ok = ok and any(len(_events(o,'revision','return')) >= 2 for o in active)
    elif pattern in ('D','H'):
        role = 'generate' if pattern=='D' else 'retain'
        saw_call = False; ok = True
        for o in active:
            source = _events(o,'items','return'); consumers = _events(o,role,'call')
            if not consumers: continue
            saw_call = True
            if len(consumers)!=1 or not source: ok=False;continue
            original, selected = source[0].get('result'), consumers[0]['args'][1]
            if (not isinstance(original,list) or not isinstance(selected,list)
                    or any(not isinstance(x,dict) or not isinstance(x.get('id'),str)
                           for x in original + selected)):
                ok=False;continue
            if len({x['id'] for x in original}) != len(original) or len({x['id'] for x in selected}) != len(selected):
                ok=False;continue
            known = {x['id']:x for x in original}
            if any(x['id'] not in known or x != known[x['id']] for x in selected): ok=False
            required = {x['id'] for x in original if (x.get('pinned') is True if pattern=='H' else x.get('contradictory') is True or x.get('uncertain') is True)}
            if not required <= {x['id'] for x in selected}: ok=False
            if pattern=='D' and any(not x.get('provenance') for x in selected):ok=False
            if pattern=='H' and (not isinstance(consumers[0]['args'][0],dict)
                    or consumers[0]['args'][0].get(spec['policy']['choice_field'])!='/prune'):ok=False
        ok = ok and saw_call
    elif pattern == 'E':
        ok = True; saw = False
        for row in results:
            if row['mode']!='active' or row['status']!='passed':continue
            o=row['observation']; before=baseline_results[row['case_id']]['observation']
            if _effects(o,spec) != _effects(before,spec):ok=False
            calls=_events(o,'finish','call');seen=_events(o,'observe','return')
            if calls and len(seen)>=2:
                saw=True
                if len(calls)!=1:ok=False
                # A verifier that only returns True cannot supply this observed state transition.
                if calls[0]['args'][2]==spec['policy']['success_action'] and seen[0].get('result')==seen[-1].get('result'):ok=False
        ok = ok and saw
    elif pattern == 'F':
        ok = all(o['outcome']['exception'] is None and o['model_calls'] <= o['handler_calls'] for o in active)
    elif pattern == 'G':
        ok = all(sum(_effects(o,spec).values()) <= spec['policy']['max_steps'] and _events(o,'finish','call') for o in active)
    elif pattern in ('K','M'):
        role='checks' if pattern=='K' else 'verify_claims'
        values=('accept','inspect','comment','request_changes') if pattern=='K' else ('accept','inspect','revise')
        ok = all(o['outcome']['result'] in values and not any(_effects(o,spec).values()) and _events(o,role,'return') for o in active)
    if ok: checks.append(RECIPES[spec['recipe']['id']].contract)
    return checks


def verify_implementation(root, bundle, phase, *, approve_execution=False, baseline_sha256=None):
    if approve_execution is not True:
        raise InputError('Missing scope: target execution; planning and status never run host code')
    if phase not in ('baseline','modified'): raise InputError('Verification phase must be baseline or modified')
    root,bundle,plan,spec,_,_ = _load(root,bundle,current_engine=True)
    with _lock(bundle):
        state = 'baseline' if phase=='baseline' else 'applied'
        if any(_inspect_file(root,r)!=state for r in plan['owned_files']):
            raise InputError('Verification files differ from the requested phase')
        _check_discovery(root,plan,applied=phase=='modified')
        baseline_rows = {}
        if phase=='modified':
            if not baseline_sha256: raise InputError('Modified verification requires the externally retained baseline receipt digest')
            baseline=_receipt(root,bundle,plan,spec,'baseline',baseline_sha256)
            if baseline['status']!='passed':raise InputError('Baseline did not pass')
            baseline_rows={r['case_id']:r for r in baseline['results']}
        started=utc_now(); results=[]
        # A crash or interruption in either phase cannot leave older success
        # current, including a baseline receipt that would authorize apply.
        _record(bundle, plan, 'verification_started' if phase == 'modified' else 'baseline_verification_started')
        for case in spec['verification']['cases']:
            for mode in (('baseline',) if phase=='baseline' else ('off','shadow','active')):
                try:
                    observation,execution_status=_probe(root,bundle,plan,spec,case,mode)
                    if execution_status not in ('passed', 'failed', 'timeout', 'not_run'):
                        raise InputError('Unknown probe execution status')
                    if execution_status == 'passed':
                        validate_observation(observation, spec)
                    else:
                        observation = None  # Unsuccessful execution cannot supply passing evidence.
                except (ValueError, TypeError, OSError, RecursionError):
                    # Bad output and raced/unavailable source remain scheduled
                    # failures. Never save an unvalidated observation or its data.
                    observation,execution_status=None,'failed'
                assertions=[]
                if observation is not None:
                    expected=case['active'] if mode=='active' else case['baseline']
                    assertions=_expected(observation,expected)
                    passed=len(assertions)==4
                    if mode!='baseline':
                        reached=(observation['adapter_calls']>0 and observation['adapter_calls']==observation['calls'].get(spec['source']['symbol'],0))
                        if reached:assertions.append('modified_host_reaches_adapter')
                        else:passed=False
                    if mode in ('off','shadow'):
                        if _observable(observation,spec)==_observable(baseline_rows[case['id']]['observation'],spec):assertions.append('baseline_parity')
                        else:passed=False
                        if mode=='off' and observation['model_calls']!=0:passed=False
                    if observation['trace_truncated'] or observation['network_attempts_denied']:passed=False
                    execution_status='passed' if passed else 'failed'
                results.append({'case_id':case['id'],'mode':mode,'status':execution_status,
                                'observation':observation,'assertions':assertions,
                                'diagnostic':None if execution_status=='passed' else 'host_probe_or_behavioral_assertion_failed'})
        contracts=[]
        if phase=='modified':contracts=_contract_assertions(results,spec,baseline_rows)
        command=spec['verification'][phase+'_command'];command_checks=[]
        if command:
            # Explicitly reviewed argv; filtered environment is NOT a sandbox.
            # This additional suite must already be trusted/externally isolated.
            try:
                check=run_authorized_tests(root,command,approve_execution=True,timeout_s=spec['verification']['timeout_s'])
            except OSError:
                # The declared runner did not start; do not echo argv/OS diagnostics.
                check={'status':'not_run', 'returncode':None}
            command_checks.append({'definition_sha256':digest(command),'status':check['status'],'returncode':check['returncode']})
        passed=all(r['status']=='passed' for r in results) and all(r['status']=='passed' for r in command_checks)
        if phase=='modified' and len(contracts)!=4:passed=False
        try:
            _check_discovery(root,plan,applied=phase=='modified')
            identity_valid=all(_inspect_file(root,row)==state for row in plan['owned_files'])
        except (InputError, OSError):
            identity_valid=False
        # The separately authorized command may change generated files or modes
        # even when its exit status is zero and every earlier scratch probe passed.
        passed=passed and identity_valid
        receipt=_bounded_receipt({'schema_version':'1.0','bundle_digest':plan['contract_digest'],'spec_digest':plan['spec_digest'],
                      'phase':phase,'engine_identity':plan['engine_identity'],'command_definition_digest':digest(spec['verification']),
                      'file_hashes':{r['file']:r['old_sha256' if phase=='baseline' else 'new_sha256'] for r in plan['owned_files']},
                      'classification':'synthetic','status':'passed' if passed else 'failed','file_identity_valid':identity_valid,'started_at':started,'finished_at':utc_now(),
                      'environment':{'python':platform.python_version(),'platform':platform.platform(),
                                     'runner_executable_sha256':file_hash(Path(sys.executable).resolve()),'sandboxed':False},
                      'scheduled_cases':len(results),'completed_cases':sum(r['status'] in ('passed','failed') for r in results),
                      'results':results,'contract_assertions':contracts,'command_checks':command_checks,
                      'baseline_receipt_sha256':baseline_sha256 if phase=='modified' else None,
                      'activation_authorized':False,'benefit_demonstrated':False})
        passed, contracts = receipt['status'] == 'passed', receipt['contract_assertions']
        validate_contract(receipt,'implementation-receipt')
        path=bundle/('baseline-receipt.json' if phase=='baseline' else 'verification-receipt.json')
        write_json(path,receipt)
        event = ('verified' if passed else 'verification_failed') if phase == 'modified' else (
            'baseline_verification_passed' if passed else 'baseline_verification_failed')
        _record(bundle, plan, event)
        return {'status':('baseline_passed' if phase=='baseline' else 'verified') if passed else 'verification_failed',
                'receipt_sha256':file_hash(path),'bundle_digest':plan['contract_digest'],
                'scheduled_cases':len(results),'passed_cases':sum(r['status']=='passed' for r in results),
                'file_identity_valid':identity_valid,
                'contract_assertions':contracts,'classification':'synthetic','runtime_activation_authorized':False,
                'benefit_demonstrated':False,'receipt_path':str(path)}
