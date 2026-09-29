"""Fresh source-bound recipe C request for the independently authored queue."""
from __future__ import annotations

import ast
from pathlib import Path

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.recipes import anchor_hash


ROOT = Path(__file__).resolve().parent
ENGINE = 'src/work_queue/engine.py'
CLI = 'src/work_queue/cli.py'
LOCK = 'src/work_queue/requirements.lock'
CONFIG = 'src/work_queue/runtime.json'
ADAPTER = 'src/work_queue/_jev_work_queue.py'


def source_matched_request(root: Path = ROOT) -> tuple[dict, dict]:
    configuration = load_config()
    inventory = scan_repo(root, configuration)
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'choose_operation')
    source = candidate['source']
    reason = ('A finite work-queue operation is ambiguous; existing host permission, '
              'approval, argument validation and effect identity remain deterministic.')
    review = {'source_sha256': source['source_sha256'], 'approved': True,
              'reviewer': 'work-queue-source-review-v1', 'reason': reason}
    apply_reviews(inventory, {candidate['candidate_id']: review}, configuration)
    for relative in (LOCK, CONFIG):
        inventory['configuration_evidence'].append(
            {'file': relative, 'sha256': file_hash(root / relative), 'markers': []})
    inventory['analysis_identity']['configuration_digest'] = digest(
        inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    statement = next(node for node in ast.parse((root / ENGINE).read_text(encoding='utf-8')).body
                     if isinstance(node, ast.FunctionDef) and node.name == 'choose_operation').body[-1]

    def expected(operation: str) -> dict:
        return {'result': 0, 'exception': None,
                'calls': {'enqueue_batch': int(operation == 'enqueue'),
                          'complete_batch': int(operation == 'complete')}, 'globals': {}}

    job = {'job_id': 'queue-probe-one', 'item': 'batch-a', 'intent': 'complete',
           'allowed': True, 'complete_allowed': True}
    spec = {
        'schema_version': '1.0', 'candidate_id': candidate['candidate_id'],
        'experiment_id': candidate['recommended_experiment']['id'],
        'inventory_sha256': digest(inventory), 'inventory_fingerprint': inventory['scan_fingerprint'],
        'source': {'file': ENGINE, 'symbol': 'choose_operation',
                   'file_sha256': source['file_sha256'],
                   'source_sha256': source['source_sha256'], 'anchor_sha256': anchor_hash(statement)},
        'recipe': {'id': 'python.C', 'version': '1.0', 'shape': 'module-tail-call-v1'},
        'bindings': {'runtime': 'runtime_for_job', 'evidence': 'evidence_for_job',
                     'baseline_action': 'base_route', 'registry': 'handlers',
                     'gate': 'gate_for_job', 'validate': 'validate_job',
                     'blocked': 'refuse_job', 'guard': 'guard_for_job'},
        'binding_review': {'approved': True, 'source_sha256': source['source_sha256'],
                           'pattern': 'C', 'reviewer': review['reviewer'], 'reason': reason},
        'questions': {'decision': {'type': 'choice',
                                   'instructions': 'Which registered queue operation fits the item and intent?',
                                   'criteria': {'enqueue': 'Put a batch into the queue.',
                                                'complete': 'Complete an approved batch.',
                                                'uncertain': 'Evidence does not select an operation.'}},
                      'sufficient': {'type': 'noul',
                                     'instructions': 'Is queue item and intent evidence sufficient?'}},
        'primary_question': 'decision', 'evidence_question': 'sufficient',
        'label_actions': {'enqueue': 'enqueue', 'complete': 'complete', 'uncertain': None},
        'policy': {'fallback': 'baseline'},
        'runtime': {'configuration': configuration['runtime'],
                    'policy_version': 'work-queue-review-v1',
                    'canary_scope': 'work-queue-offline-only', 'task_field': 'job_id',
                    'max_evidence_bytes': 4096, 'cost_upper_bound': 0.0,
                    'ownership': 'stable_host', 'coordinator': 'shared_process_local',
                    'task_completion': 'host_owned', 'audit': 'required', 'immutable_cache': False},
        'output': {'module': '_jev_work_queue',
                   'permitted_edits': [ENGINE, ADAPTER, LOCK, CONFIG],
                   'feature_flag_default': False,
                   'dependencies': ['jev-integration-evaluator>=1.3.0.dev1']},
        'verification': {'classification': 'synthetic', 'entry_point': 'handle_job',
                         'effect_symbols': ['enqueue_batch', 'complete_batch'],
                         'cases': [{'id': 'approved_complete', 'request': job,
                                    'initial_globals': {}, 'baseline': expected('enqueue'),
                                    'active': expected('complete'),
                                    'assessment_label': 'complete'}],
                         'timeout_s': 20, 'baseline_command': [], 'modified_command': []},
        'authorization_context': {'reference': 'issue-57-work-queue-offline-preparation',
                                  'scopes': ['synthetic_workspace_only'], 'not_authority': True},
        'package_binding': {'version': '1.0', 'namespace': False,
                            'module': 'work_queue.engine'},
        'host_lifecycle': {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                           'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'},
        'runtime_files': [
            {'file': LOCK, 'kind': 'dependency_lock', 'old_sha256': file_hash(root / LOCK),
             'new_content': '# reviewed installed evaluator pin\njev-integration-evaluator==1.3.0.dev12\n'},
            {'file': CONFIG, 'kind': 'configuration', 'old_sha256': file_hash(root / CONFIG),
             'new_content': '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'},
        ],
    }
    request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
               'template_version': '1.0.0', 'backend': 'python',
               'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
               'implementation_spec': spec}
    binding = {'version': '1.0', 'script': 'work-queue',
               'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                                  'dependency_plan': 'dependencies',
                                  'startup_options': 'options'}}
    return request, binding
