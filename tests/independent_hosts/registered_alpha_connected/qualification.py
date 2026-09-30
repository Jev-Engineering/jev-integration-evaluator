"""Source-matched preparation of the independently reviewed Alpha 1.0.2 host."""
from __future__ import annotations

import ast
from pathlib import Path

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.integrations.recipes import anchor_hash


ROOT = Path(__file__).resolve().parent
HOST = 'src/registered_alpha/host.py'
CONSOLE = 'src/registered_alpha/console.py'
LOCK = 'src/registered_alpha/requirements.lock'
CONFIG = 'src/registered_alpha/runtime.json'
ADAPTER = 'src/registered_alpha/_jev_registered_alpha.py'


def source_matched_request(root: Path = ROOT) -> tuple[dict, dict]:
    """Bind only the current scanned bytes; this grants no runtime authority."""
    cfg = load_config()
    inventory = scan_repo(root, cfg)
    candidate = next(c for c in inventory['candidates']
                     if c['source']['symbol'] == 'select_registered_tool')
    source = candidate['source']
    reason = ('Finite registered-action selection is ambiguous; host-owned permission, '
              'approval, argument validation and effect ledger remain deterministic.')
    review = {'source_sha256': source['source_sha256'], 'approved': True,
              'reviewer': 'registered-alpha-connected-source-review-v1.0.2', 'reason': reason}
    apply_reviews(inventory, {candidate['candidate_id']: review}, cfg)
    # The scanner does not classify package-data lock/config as configuration
    # evidence. Add the actual old bytes to the reviewed inventory before binding.
    for relative in (LOCK, CONFIG):
        inventory['configuration_evidence'].append(
            {'file': relative, 'sha256': file_hash(root / relative), 'markers': []})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    statement = next(n for n in ast.parse((root / HOST).read_text(encoding='utf-8')).body
                     if isinstance(n, ast.FunctionDef) and n.name == 'select_registered_tool').body[-1]
    def expected(action: str) -> dict:
        return {'result': 0, 'exception': None,
                'calls': {'inspect_item': int(action == 'inspect'),
                          'summarize_item': int(action == 'summarize')}, 'globals': {}}
    request = {'task_id': 'alpha-probe-one', 'item': 'fixture-one', 'intent': 'summarize',
               'permit': True, 'approved': True}
    spec = {
        'schema_version': '1.0', 'candidate_id': candidate['candidate_id'],
        'experiment_id': candidate['recommended_experiment']['id'],
        'inventory_sha256': digest(inventory), 'inventory_fingerprint': inventory['scan_fingerprint'],
        'source': {'file': HOST, 'symbol': 'select_registered_tool',
                   'file_sha256': source['file_sha256'],
                   'source_sha256': source['source_sha256'], 'anchor_sha256': anchor_hash(statement)},
        'recipe': {'id': 'python.C', 'version': '1.0', 'shape': 'module-tail-call-v1'},
        'bindings': {'runtime': 'host_runtime', 'evidence': 'host_evidence',
                     'baseline_action': 'host_baseline_action', 'registry': 'host_registry',
                     'gate': 'host_gate', 'validate': 'host_validate',
                     'blocked': 'host_blocked', 'guard': 'host_guard'},
        'binding_review': {'approved': True, 'source_sha256': source['source_sha256'],
                           'pattern': 'C', 'reviewer': review['reviewer'], 'reason': reason},
        'questions': {'decision': {'type': 'choice',
                                   'instructions': 'Which registered action fits this item and intent?',
                                   'criteria': {'inspect': 'Inspect the finite item.',
                                                'summarize': 'Summarize the finite item.',
                                                'uncertain': 'Evidence is insufficient to select.'}},
                      'sufficient': {'type': 'noul',
                                     'instructions': 'Is the item and intent evidence sufficient?'}},
        'primary_question': 'decision', 'evidence_question': 'sufficient',
        'label_actions': {'inspect': 'inspect', 'summarize': 'summarize', 'uncertain': None},
        'policy': {'fallback': 'baseline'},
        'runtime': {'configuration': cfg['runtime'], 'policy_version': 'registered-alpha-review-v1',
                    'canary_scope': 'registered-alpha-offline-only', 'task_field': 'task_id',
                    'max_evidence_bytes': 4096, 'cost_upper_bound': 0.0,
                    'ownership': 'stable_host', 'coordinator': 'shared_process_local',
                    'task_completion': 'host_owned', 'audit': 'required', 'immutable_cache': False},
        'output': {'module': '_jev_registered_alpha',
                   'permitted_edits': [HOST, ADAPTER, LOCK, CONFIG],
                   'feature_flag_default': False,
                   'dependencies': ['jev-integration-evaluator>=1.3.0.dev1']},
        'verification': {'classification': 'synthetic', 'entry_point': 'public_entry',
                         'effect_symbols': ['inspect_item', 'summarize_item'],
                         'cases': [{'id': 'approved_summarize', 'request': request,
                                    'initial_globals': {}, 'baseline': expected('inspect'),
                                    'active': expected('summarize'),
                                    'assessment_label': 'summarize'}],
                         'timeout_s': 20, 'baseline_command': [], 'modified_command': []},
        'authorization_context': {'reference': 'issue-57-authorized-offline-fixture-preparation',
                                  'scopes': ['synthetic_workspace_only'], 'not_authority': True},
        'package_binding': {'version': '1.0', 'namespace': False,
                            'module': 'registered_alpha.host'},
        'host_lifecycle': {'kind': 'module-startup-v1', 'startup': 'start_jev_runtime',
                           'shutdown': 'stop_jev_runtime', 'complete_task': 'finish_jev_task'},
        'runtime_files': [
            {'file': LOCK, 'kind': 'dependency_lock', 'old_sha256': file_hash(root / LOCK),
             'new_content': '# reviewed installed evaluator pin\njev-integration-evaluator==1.3.0.dev12\n'},
            {'file': CONFIG, 'kind': 'configuration', 'old_sha256': file_hash(root / CONFIG),
             'new_content': '{"jev_runtime":{"mode":"off","credential_ref":"env:TYPESAFE_API_KEY"}}\n'}],
    }
    template_request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
                        'template_version': '1.0.0', 'backend': 'python',
                        'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
                        'implementation_spec': spec}
    console_binding = {'version': '1.0', 'script': 'registered-alpha',
                       'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                                          'dependency_plan': 'dependencies',
                                          'startup_options': 'options'}}
    return template_request, console_binding
