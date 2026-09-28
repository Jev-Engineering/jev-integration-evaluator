"""Private offline test subprocess, NOT a production activation interface.

The synthetic fixture below exercises the existing receipt checks, exactly as the
legacy runtime unit tests do. Its temporary receipt is never saved or exported as
observed evidence. Generated integrations contain no fixture/activation bypass.
A Python audit hook is defense in depth, NOT an operating-system security sandbox.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import importlib.util
import importlib
from pathlib import Path
import sys

from ..budget import BudgetCoordinator
from ..io import digest, canonical, read_json, write_json
from ..robustness import request_fingerprint
from .package_bindings import StaticBindings, module_layout


def _plain(value, depth=0):
    if depth > 20: return False
    if type(value) in (str, int, float, bool, type(None)): return True
    if type(value) is list: return len(value) <= 4096 and all(_plain(x, depth+1) for x in value)
    if type(value) is dict:
        return len(value) <= 4096 and all(type(k) is str and _plain(v, depth+1) for k,v in value.items())
    return False


class SyntheticClient:
    is_remote = False
    evidence_type = 'synthetic'
    def __init__(self, label): self.label, self.calls = label, 0
    def evaluate(self, state, questions, model, timeout_ms):
        self.calls += 1
        answers = {}
        for key, q in questions.items():
            if q['type'] == 'choice':
                selected = self.label if self.label in q['criteria'] else next(iter(q['criteria']))
                answers[key] = {'type':'choice', 'choice':selected, 'confidence':1.0,
                                'probabilities':{k:float(k==selected) for k in q['criteria']}}
            elif q['type'] == 'noul': answers[key] = {'type':'noul','noul':1.0}
            else:
                raise ValueError('Synthetic implementation probes require Choice/Noul questions')
        return {'model':model, 'answers':answers, 'usage':{'input_tokens':1,'output_tokens':1}}


class SyntheticAudit:
    def __init__(self): self.events = []
    def append(self, event):
        if len(self.events) >= 1024: raise ValueError('Synthetic audit bound')
        self.events.append(copy.deepcopy(event))


def _fixture_receipt(router, spec):
    """Test-only legacy receipt-shaped fixture; outer execution classification is synthetic."""
    now = datetime.now(timezone.utc)
    questions = spec['questions']
    return {'approved':True,'calibration_validated':True,'model':router.config['model'],
            'policy_version':router.policy_version,'questions_hash':digest(questions),
            'thresholds_hash':digest(asdict(router.thresholds)), 'holdout_evidence_ref':'SYNTHETIC-UNIT-FIXTURE-NOT-DEPLOYMENT',
            'activation_id':'SYNTHETIC-UNIT-FIXTURE-NOT-DEPLOYMENT','evidence_type':'observed',
            'issued_at':(now-timedelta(minutes=1)).isoformat(),'expires_at':(now+timedelta(minutes=2)).isoformat(),
            'ordered_questions_hash':request_fingerprint(None,questions,router.config['model']),
            'runtime_contract_hash':router.runtime_contract_hash(questions,spec['primary_question'],spec['evidence_question'],label_actions=spec['label_actions'])}


def _check_target_import_origin(import_root: Path, module_name: str, namespace: bool) -> None:
    top = module_name.split('.')[0]
    if top in sys.modules:
        raise ValueError('Target package name is already loaded by the trusted runner')
    top_spec = importlib.util.find_spec(top)
    expected_init = (import_root / top / '__init__.py').resolve()
    expected_namespace = (import_root / top).resolve()
    if top_spec is None or (top_spec.origin is not None and Path(top_spec.origin).resolve() != expected_init):
        raise ValueError('Target package resolves outside the copied reviewed source')
    if top_spec.origin is None and (not namespace or
            {Path(p).resolve() for p in top_spec.submodule_search_locations or []} != {expected_namespace}):
        raise ValueError('Namespace package resolution differs from the copied reviewed source')


def run(payload):
    spec, case, mode = payload['spec'], payload['case'], payload['mode']
    if spec['verification']['classification'] != 'synthetic':
        raise ValueError('This subprocess is only an explicitly authorized synthetic probe')
    root = Path(payload['root']).resolve()
    network_attempts = []
    def deny_network(event, args):
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            network_attempts.append(event)
            raise PermissionError('Offline probe denies network and child process creation')
    sys.addaudithook(deny_network)
    # Isolated interpreter; trusted evaluator imported first. Target modules are
    # appended, not allowed to shadow the tool or standard-library search roots.
    package_contract = spec.get('package_binding')
    sys.path.append(str(root))
    if package_contract and spec['source']['file'].startswith('src/'):
        sys.path.append(str(root / 'src'))
    source = root / spec['source']['file']
    if package_contract:
        _, module_name, _ = module_layout(root, spec['source']['file'], namespace=package_contract['namespace'])
        if module_name != package_contract['module']:
            raise ValueError('Declared target module differs from copied source path')
        import_root = root / 'src' if spec['source']['file'].startswith('src/') else root
        _check_target_import_origin(import_root, module_name, package_contract['namespace'])
        module = importlib.import_module(module_name)
        if Path(module.__file__).resolve() != source.resolve():
            raise ValueError('Target module import origin differs from the copied reviewed source')
    else:
        loader_spec = importlib.util.spec_from_file_location(source.stem, source)
        module = importlib.util.module_from_spec(loader_spec)
        sys.modules[source.stem] = module
        loader_spec.loader.exec_module(module)
    for name, value in case['initial_globals'].items():
        if name.startswith('__') or name not in module.__dict__ or not _plain(module.__dict__[name]):
            raise ValueError('Fixture initialization may only replace existing JSON data globals')
        module.__dict__[name] = copy.deepcopy(value)
    adapter_path = root / (spec['output']['module'] + '.py') if not package_contract else source.parent / (spec['output']['module'] + '.py')
    router, client = None, SyntheticClient(case['assessment_label'])
    if mode != 'baseline':
        adapter_name = spec['output']['module'] if not package_contract else module_name.rpartition('.')[0] + '.' + spec['output']['module']
        adapter = sys.modules.get(adapter_name)
        if adapter is None: raise ValueError('Modified host did not import its generated adapter')
        adapter.ENABLED = mode != 'off'
        if mode in ('shadow', 'active'):
            cfg = copy.deepcopy(spec['runtime']['configuration']); cfg['mode'] = mode
            ledger = BudgetCoordinator(max_calls_per_task=32,max_cost_per_task=10,max_total_calls=64,
                                       max_total_cost=20,max_in_flight=8,max_tasks=64)
            router = adapter.create_router(client,budget_coordinator=ledger,audit_log=SyntheticAudit(),runtime_config=cfg)
            if mode == 'active': router.activation = _fixture_receipt(router, spec)
            module.__dict__[spec['bindings']['runtime']] = lambda request: router
    calls, adapter_calls, handler_calls = Counter(), 0, 0
    trace, trace_truncated = [], False
    roles = {name:role for role,name in spec['bindings'].items()}
    profile_sources = {str(source)}
    profile_aliases = {}
    if package_contract:
        profile_sources.update(str(root / rel) for rel in payload.get('contributing_sources', {}))
        static = StaticBindings(root, spec['source']['file'], namespace=package_contract['namespace'])
        for alias in [*spec['bindings'].values(), *spec['verification']['effect_symbols']]:
            rel, actual, _ = static.resolve(alias)
            key = (str(root / rel), actual)
            if key in profile_aliases and profile_aliases[key] != alias:
                raise ValueError('Ambiguous imported observation aliases')
            profile_aliases[key] = alias
    traced_roles = {'items','generate','retain','observe','postcondition','finish','gate','validate','risk','revision','reserve_retry','effect_state','ownership','verify_child','checks','verify_claims'}
    handler_name = '_action_' + spec['recipe']['id'].split('.')[-1].lower()
    host_runtime_path = str(Path(__file__).with_name('host.py'))
    def profile(frame, event, argument):
        nonlocal adapter_calls, handler_calls, trace_truncated
        if event not in ('call','return'): return
        filename, name = frame.f_code.co_filename, frame.f_code.co_name
        observed_name = profile_aliases.get((filename, name), name)
        if filename in profile_sources:
            if event == 'call': calls[observed_name] += 1
            role = roles.get(observed_name)
            if role in traced_roles:
                entry = {'role':role,'event':event}
                if event == 'call':
                    values = [frame.f_locals.get(k) for k in frame.f_code.co_varnames[:frame.f_code.co_argcount]]
                    entry['args'] = [copy.deepcopy(v) if _plain(v) else None for v in values]
                elif _plain(argument): entry['result'] = copy.deepcopy(argument)
                if len(trace) < 512 and len(canonical(entry)) <= 200000: trace.append(entry)
                else: trace_truncated = True
        elif event == 'call' and filename == str(adapter_path) and name == 'invoke': adapter_calls += 1
        elif event == 'call' and filename == host_runtime_path and name == handler_name: handler_calls += 1
        if sum(calls.values()) > 100_000: raise RuntimeError('Probe call bound exceeded')
    sys.setprofile(profile)
    try:
        result = module.__dict__[spec['verification']['entry_point']](copy.deepcopy(case['request']))
        if not _plain(result): raise ValueError('Unsupported non-JSON verification result')
        canonical(result)
        outcome = {'result':copy.deepcopy(result),'exception':None,'exception_message_sha256':None}
    except Exception as exc:
        outcome = {'result':None,'exception':type(exc).__name__,'exception_message_sha256':digest(str(exc))}
    finally:
        sys.setprofile(None)
        if router is not None: router.close()
    observations = {k:copy.deepcopy(v) for k,v in module.__dict__.items()
                    if not k.startswith('__') and _plain(v)}
    if len(canonical(observations)) > 1_000_000: raise ValueError('Global observation byte bound exceeded')
    return {'outcome':outcome,'calls':dict(calls),'globals':observations,'adapter_calls':adapter_calls,
            'handler_calls':handler_calls,'model_calls':client.calls,'network_attempts_denied':len(network_attempts),
            'classification':'synthetic','trace':trace,'trace_truncated':trace_truncated}


def main():
    input_path, output_path = sys.argv[1:]
    payload = read_json(Path(input_path))
    write_json(Path(output_path), run(payload))


if __name__ == '__main__': main()
