"""Source-bound D console caller; installed retrieval effects have a separate journey."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, file_hash
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.contracts import validate_spec
from jev_integration_evaluator.integrations.lifecycle import (
    apply_implementation, plan_implementation, rollback_implementation,
)
from jev_integration_evaluator.integrations.verification import verify_implementation
from tests.test_use_case_retrieval_host import PROFILE, _host, _corpus


BINDING = {'version': '1.0', 'script': 'retrieval-host',
           'startup_inputs': {'budget_limits': 'limits', 'audit_log': 'audit',
                              'dependency_plan': 'dependencies', 'startup_options': 'options'}}
pytestmark = pytest.mark.skipif(not PROFILE, reason='D source-bound bind fixture requires Linux x86-64 CPython 3.13')


def _bound_host(target: Path) -> tuple[dict, dict]:
    _, spec, request = _host(target, '1.0.0')
    entry = spec['verification']['entry_point']
    console = target / 'retrieval_host/console.py'
    console.write_text(
        f'from .{Path(spec["source"]["file"]).stem} import {entry}\n'
        'from pathlib import Path\nimport hashlib\n'
        'class Audit:\n'
        '    def __init__(self): self.records = []\n'
        '    def append(self, record): self.records.append(record)\n'
        'def limits():\n'
        '    return dict(max_calls_per_task=2, max_cost_per_task=2, '
        'max_total_calls=2, max_total_cost=2, max_in_flight=1, max_tasks=1)\n'
        'def audit():\n    return Audit()\n'
        'def dependencies():\n'
        '    base = Path(__file__).resolve().parent\n'
        "    return {'files': [{'path': str(base / name), 'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest()} for name in ('requirements.lock', 'runtime.json')]}\n"
        'def options():\n    return {}\n'
        'def make_requests():\n'
        "    return [{'task_id': 'retrieval-task', 'query': 'approved', 'expected_revision': 7}]\n"
        'def main():\n'
        '    requests = make_requests()\n'
        '    for request in requests:\n'
        f'        {entry}(request)\n'
        '    return 0\n'
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding='utf-8')
    runtime_files = {
        'requirements.lock': ('dependency_lock', 'jev-integration-evaluator==1.3.0.dev1\n',
                              'jev-integration-evaluator==1.3.0.dev12\n'),
        'runtime.json': ('configuration', '{"jev_runtime":{"mode":"off","credential_ref":null}}\n',
                         '{"jev_runtime":{"mode":"off","credential_ref":null,"feature_flag":false}}\n'),
    }
    for name, (kind, old, new) in runtime_files.items():
        path = target / 'retrieval_host' / name
        path.write_text(old, encoding='utf-8')
        relative = path.relative_to(target).as_posix()
        spec.setdefault('runtime_files', []).append({
            'file': relative, 'kind': kind,
            'old_sha256': hashlib.sha256(old.encode()).hexdigest(), 'new_content': new})
        spec['output']['permitted_edits'].append(relative)
    spec['host_lifecycle'] = {'kind': 'module-startup-v1',
                              'startup': 'start_jev_runtime', 'shutdown': 'stop_jev_runtime',
                              'complete_task': 'finish_jev_task'}
    project = target / 'pyproject.toml'
    project.write_text(project.read_text(encoding='utf-8') +
        '[tool.setuptools.package-data]\nretrieval_host = ["*.lock", "*.json"]\n',
        encoding='utf-8')
    cfg = load_config()
    cfg['repository']['typescript_ast'] = False
    inventory = scan_repo(target, cfg)
    candidate = next(row for row in inventory['candidates']
                     if row['source']['symbol'] == 'select_boundary_retrieval_handoff')
    reason = ('Reviewed D caller has one task call per bounded request; '
              'code-owned corpus, provenance, conflict and answer gates remain outside this binder')
    apply_reviews(inventory, {candidate['candidate_id']: {
        'source_sha256': candidate['source']['source_sha256'], 'approved': True,
        'reviewer': 'offline-retrieval-bind-author', 'reason': reason}}, cfg)
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['source'].update({'file_sha256': candidate['source']['file_sha256'],
                           'source_sha256': candidate['source']['source_sha256']})
    spec['binding_review'].update({'source_sha256': candidate['source']['source_sha256'],
                                   'reason': reason})
    for name, (kind, old, _) in runtime_files.items():
        inventory['configuration_evidence'].append({
            'file': 'retrieval_host/' + name,
            'sha256': hashlib.sha256(old.encode()).hexdigest()})
    inventory['analysis_identity']['configuration_digest'] = digest(inventory['configuration_evidence'])
    inventory['scan_fingerprint'] = digest(inventory['analysis_identity'])
    spec['inventory_sha256'] = digest(inventory)
    spec['inventory_fingerprint'] = inventory['scan_fingerprint']
    request['reviewed_inventory'] = inventory
    request['implementation_spec'] = spec
    return inventory, request


def test_d_bound_console_source_and_owned_edit(tmp_path, monkeypatch):
    target = tmp_path / 'host'
    inventory, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    entry = prepared['request']['implementation_spec']['entrypoint_binding']
    assert entry['kind'] == 'task-loop-v1'
    assert entry['file'] == 'retrieval_host/console.py'
    assert entry['pyproject_sha256'] == file_hash(target / 'pyproject.toml')
    bound = prepared['request']
    assert validate_template_request(target, bound)['status'] == 'validated'
    report = bind_template(target, request, BINDING, tmp_path / 'bound')
    assert report['request_sha256'] == digest(bound)
    assert json.loads((tmp_path / 'bound/template-request.json').read_text()) == bound
    materialize_template(target, bound, tmp_path / 'template')
    spec = bound['implementation_spec']
    preimages = {name: (target / name).read_bytes() for name in (
        spec['source']['file'], 'retrieval_host/console.py',
        'retrieval_host/requirements.lock', 'retrieval_host/runtime.json',
        'retrieval_host/retrieval_consumer.py')}
    corpus = _corpus(tmp_path, 'bound-corpus')
    monkeypatch.setenv('D_CORPUS_PATH', str(corpus))
    monkeypatch.setenv('D_EFFECT_PATH', str(tmp_path / 'effect-{pid}.json'))
    bundle = tmp_path / 'bundle'
    planned = plan_implementation(target, inventory, spec['candidate_id'], spec, bundle)
    baseline = verify_implementation(target, bundle, 'baseline', approve_execution=True)
    assert baseline['status'] == 'baseline_passed'
    applied = apply_implementation(target, bundle, planned['bundle_digest'],
                                   baseline_sha256=baseline['receipt_sha256'])
    modified = verify_implementation(target, bundle, 'modified', approve_execution=True,
                                     baseline_sha256=baseline['receipt_sha256'])
    assert modified['status'] == 'verified'
    effects = sorted(tmp_path.glob('effect-*.json'))
    assert len(effects) >= 2
    assert all(json.loads(path.read_text())['answer']['disposition'] == 'withheld_conflict'
               for path in effects)
    assert b'start_jev_runtime' in (target / 'retrieval_host/console.py').read_bytes()
    assert rollback_implementation(target, bundle, applied['rollback_digest'])['status'] == 'rolled_back'
    assert {name: (target / name).read_bytes() for name in preimages} == preimages


def test_d_bound_console_rejects_drift_and_single_call(tmp_path):
    target = tmp_path / 'host'
    _, request = _bound_host(target)
    prepared = prepare_template_binding(target, request, BINDING)
    invalid = copy.deepcopy(prepared['request']['implementation_spec'])
    invalid['entrypoint_binding']['kind'] = 'single-request-v1'
    with pytest.raises(InputError, match='Invalid implementation specification'):
        validate_spec(invalid)
    console = target / 'retrieval_host/console.py'
    original = console.read_bytes()
    console.write_bytes(original + b'\n# unreviewed caller\n')
    with pytest.raises(InputError, match='drift|changed'):
        validate_template_request(target, prepared['request'])
    console.write_bytes(original)
    entry = request['implementation_spec']['verification']['entry_point']
    single = original.decode().replace(
        '    requests = make_requests()\n    for request in requests:\n'
        f'        {entry}(request)\n    return 0\n',
        '    request = make_requests()\n'
        f'    return {entry}(request)\n')
    assert single != original.decode()
    console.write_text(single, encoding='utf-8')
    with pytest.raises(UnsupportedShape, match='bounded explicit request loop'):
        prepare_template_binding(target, request, BINDING)
