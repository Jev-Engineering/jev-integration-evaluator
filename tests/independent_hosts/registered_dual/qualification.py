"""Fresh two-seam source review for one existing dual registered-action console."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.integrations.python_entrypoint import inspect_entrypoint
from jev_integration_evaluator.integrations.recipes import anchor_hash
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews


ROOT = Path(__file__).resolve().parent
PACKAGE = 'src/registered_dual/'
LOCK, CONFIG = PACKAGE + 'requirements.lock', PACKAGE + 'runtime.json'
CONSOLE = PACKAGE + 'console.py'
SEAMS = (
    ('alpha', 'select_registered_tool', 'registered-dual', 'public_entry',
     'host_runtime', 'host_evidence', 'host_baseline_action', 'host_registry',
     'host_gate', 'host_validate', 'host_blocked', 'host_guard',
     'inspect_item', 'summarize_item', 'inspect', 'summarize'),
    ('work_queue', 'choose_operation', 'registered-dual-queue', 'handle_job',
     'runtime_for_job', 'evidence_for_job', 'base_route', 'handlers',
     'gate_for_job', 'validate_job', 'refuse_job', 'guard_for_job',
     'enqueue_batch', 'complete_batch', 'enqueue', 'complete'),
)


def source_matched_composite(root: Path = ROOT) -> tuple[dict, dict, dict]:
    cfg = load_config()
    cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(root, cfg)
    chosen = {}
    reviews = {}
    for seam in SEAMS:
        module, symbol = seam[:2]
        matches = [row for row in inventory['candidates']
                   if row['source']['file'] == PACKAGE + module + '.py'
                   and row['source']['symbol'] == symbol]
        if len(matches) != 1:
            raise RuntimeError('dual_reviewed_candidate_missing:' + symbol)
        candidate = matches[0]
        chosen[module] = candidate
        reviews[candidate['candidate_id']] = {
            'source_sha256': candidate['source']['source_sha256'], 'approved': True,
            'reviewer': 'registered-dual-source-review-v1',
            'reason': 'Finite existing operation; host permission, approval and effects remain code owned.'}
    apply_reviews(inventory, reviews, cfg)
    for relative in (LOCK, CONFIG):
        inventory['configuration_evidence'].append(
            {'file': relative, 'sha256': file_hash(root / relative), 'markers': []})
    inventory['analysis_identity']['configuration_digest'] = digest(
        inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    specs = {}
    request = {'task_id': 'dual-probe', 'item': 'fixture-one', 'intent': 'summarize',
               'permit': True, 'approved': True, 'allowed': True,
               'complete_allowed': True}
    for seam in SEAMS:
        (module, symbol, script, entry, runtime, evidence, baseline_action,
         registry, gate, validate, blocked, guard, first, second,
         baseline, alternate) = seam
        candidate = chosen[module]
        source = candidate['source']
        source_file = PACKAGE + module + '.py'
        adapter = PACKAGE + '_jev_' + module + '.py'
        statement = next(row for row in ast.parse((root / source_file).read_text()).body
                         if isinstance(row, ast.FunctionDef) and row.name == symbol).body[-1]
        def expected(action):
            return {'result': 0, 'exception': None,
                    'calls': {first: int(action == baseline),
                              second: int(action == alternate)}, 'globals': {}}
        spec = {
            'schema_version': '1.0', 'candidate_id': candidate['candidate_id'],
            'experiment_id': candidate['recommended_experiment']['id'],
            'inventory_sha256': digest(inventory),
            'inventory_fingerprint': inventory['scan_fingerprint'],
            'source': {'file': source_file, 'symbol': symbol,
                       'file_sha256': source['file_sha256'],
                       'source_sha256': source['source_sha256'],
                       'anchor_sha256': anchor_hash(statement)},
            'recipe': {'id': 'python.C', 'version': '1.0', 'shape': 'module-tail-call-v1'},
            'bindings': {'runtime': runtime, 'evidence': evidence,
                         'baseline_action': baseline_action, 'registry': registry,
                         'gate': gate, 'validate': validate,
                         'blocked': blocked, 'guard': guard},
            'binding_review': {'approved': True, 'source_sha256': source['source_sha256'],
                               'pattern': 'C', 'reviewer': 'registered-dual-source-review-v1',
                               'reason': reviews[candidate['candidate_id']]['reason']},
            'questions': {'decision': {'type': 'choice',
                                       'instructions': 'Which finite action matches the task?',
                                       'criteria': {baseline: 'Existing baseline action.',
                                                    alternate: 'Approved alternative action.',
                                                    'uncertain': 'Insufficient evidence.'}},
                          'sufficient': {'type': 'noul',
                                         'instructions': 'Is the task evidence sufficient?'}},
            'primary_question': 'decision', 'evidence_question': 'sufficient',
            'label_actions': {baseline: baseline, alternate: alternate,
                              'uncertain': None},
            'policy': {'fallback': 'baseline'},
            'runtime': {'configuration': {**cfg['runtime'], 'max_calls_per_task': 2,
                                          'max_cost_per_task': 2},
                        'policy_version': 'registered-dual-review-v1',
                        'canary_scope': 'registered-dual-offline-only',
                        'task_field': 'task_id', 'max_evidence_bytes': 4096,
                        'cost_upper_bound': 0.0, 'ownership': 'stable_host',
                        'coordinator': 'shared_process_local',
                        'task_completion': 'host_owned', 'audit': 'required',
                        'immutable_cache': False},
            'output': {'module': '_jev_' + module,
                       'permitted_edits': [source_file, adapter, LOCK, CONFIG, CONSOLE],
                       'feature_flag_default': False,
                       'dependencies': ['jev-integration-evaluator>=1.3.0.dev1']},
            'verification': {'classification': 'synthetic', 'entry_point': entry,
                             'effect_symbols': [first, second],
                             'cases': [{'id': 'approved_' + alternate,
                                        'request': request, 'initial_globals': {},
                                        'baseline': expected(baseline),
                                        'active': expected(alternate),
                                        'assessment_label': alternate}],
                             'timeout_s': 20, 'baseline_command': [],
                             'modified_command': []},
            'authorization_context': {'reference': 'issue-57-dual-offline-fixture',
                                      'scopes': ['synthetic_workspace_only'],
                                      'not_authority': True},
            'package_binding': {'version': '1.0', 'namespace': False,
                                'module': 'registered_dual.' + module},
            'host_lifecycle': {'kind': 'module-startup-v1',
                               'startup': 'start_jev_runtime',
                               'shutdown': 'stop_jev_runtime',
                               'complete_task': 'finish_jev_task'},
            'runtime_files': [
                {'file': LOCK, 'kind': 'dependency_lock',
                 'old_sha256': file_hash(root / LOCK),
                 'new_content': '# reviewed installed evaluator pin\njev-integration-evaluator==1.3.0.dev12\n'},
                {'file': CONFIG, 'kind': 'configuration',
                 'old_sha256': file_hash(root / CONFIG),
                 'new_content': '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'},
            ],
        }
        input_name = 'queue' if module == 'work_queue' else module
        binding = {'version': '1.0', 'script': script,
                   'startup_inputs': {'budget_limits': 'limits_' + input_name,
                                      'audit_log': 'audit_' + input_name,
                                      'dependency_plan': 'dependencies_' + input_name,
                                      'startup_options': 'options_' + input_name}}
        spec['entrypoint_binding'] = inspect_entrypoint(root, spec, binding)
        specs[candidate['candidate_id']] = spec
    ids = sorted(specs)
    evaluator = Path(importlib.util.find_spec('jev_integration_evaluator').origin).resolve().parent.parent
    primary = specs[ids[0]]['entrypoint_binding']['function']
    code = ('import json,sys;sys.path.insert(0,' + repr(str(root / 'src')) + ');'
            'sys.path.insert(0,' + repr(str(evaluator)) + ');'
            'from registered_dual import console;'
            'assert getattr(console,' + repr(primary) + ')()==0;'
            'assessed=sorted(row["candidate_id"] for row in console.EVENTS '
            'if row.get("type")=="assessment");'
            'seen=console.OBSERVATION;'
            'assert assessed==' + repr(ids) + ';'
            'print(json.dumps({"schema_version":"composite-host-observation-v1",'
            '"candidate_ids":' + repr(ids) + ',"task_id":"dual-probe",'
            '"coordinator_tokens":seen["tokens"],"canary_scopes":seen["scopes"],'
            '"assessment_calls":seen["calls"],"total_cost":seen["cost"],'
            '"audit_candidate_ids":assessed,"results":' + repr({key: 0 for key in ids}) + '}))')
    selection = {'schema_version': 'composite-selection-v1', 'candidate_ids': ids,
                 'dependencies': [], 'conflicts': [],
                 'shared_runtime': {'task_field': 'task_id',
                                    'policy_version': 'registered-dual-review-v1',
                                    'canary_scope': 'registered-dual-offline-only',
                                    'max_calls_per_task': 2, 'max_cost_per_task': 2},
                 'combined_verification': {'command': [sys.executable, '-I', '-c', code],
                                           'shared_task_id': 'dual-probe',
                                           'expected_results': {key: 0 for key in ids}}}
    return inventory, selection, specs
