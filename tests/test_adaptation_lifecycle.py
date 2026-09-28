"""Synthetic local state tests; native receipt security is tested by runner suites."""
import ast
import hashlib
from pathlib import Path

import pytest

from jev_integration_evaluator.integrations import adaptation_lifecycle as life
from jev_integration_evaluator.io import InputError, digest


HOST = '''import adapter
events = []
class Worker:
    def baseline(self, request):
        events.append(request)
        return request
    def run(self, request):
        return self.baseline(request)
'''
ADAPTER = '''def invoke(original, request):
    return original(request)
'''


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path):
    root = tmp_path / 'host'; root.mkdir()
    host, adapter = root / 'host.py', root / 'adapter.py'
    host.write_bytes(HOST.encode()); adapter.write_bytes(ADAPTER.encode())
    source_sha, adapter_sha = _hash(HOST.encode()), _hash(ADAPTER.encode())
    statement = ast.parse(HOST).body[-1].body[-1].body[-1]
    source = {'file': 'host.py', 'symbol': 'Worker.run', 'source_sha256': 'a'*64,
              'file_sha256': source_sha,
              'anchor_sha256': digest(ast.dump(statement, annotate_fields=True, include_attributes=False))}
    analysis = {'test': 'synthetic'}
    inventory = {'analysis_identity': analysis, 'scan_fingerprint': digest(analysis),
                 'files': [{'file': 'host.py', 'sha256': source_sha},
                           {'file': 'adapter.py', 'sha256': adapter_sha}], 'configuration_evidence': [],
                 'candidates': [{'candidate_id': 'c', 'source': {k:source[k] for k in
                                 ('file', 'symbol', 'source_sha256', 'file_sha256')},
                                 'pattern': 'C', 'tier': 1,
                                 'semantic_review': {'approved': True, 'reviewer': 'test',
                                     'reason': 'synthetic review', 'source_sha256': 'a'*64}}]}
    request = {'strategy': {'shape': 'instance-method-tail-call-v1', 'version': '1.0'},
               'candidate_id': 'c', 'inventory_sha256': digest(inventory),
               'inventory_fingerprint': digest(analysis), 'source': source,
               'binding_review': {'reviewer': 'test', 'reason': 'synthetic binding review',
                   'source_sha256': 'a'*64, 'adapter_file': 'adapter.py',
                   'adapter_sha256': adapter_sha}, 'adapter_name': 'adapter'}
    bundle = tmp_path / 'private'
    plan = life.plan_adaptation(root, inventory, request, bundle)
    oracle = {'schema_version': '1.0', 'kind': 'native-postconditions-v1',
              'repository_identity': digest(str(root.resolve())),
              'context_sha256': digest({'inventory_sha256': digest(inventory),
                                        'request_sha256': digest(request)}),
              'bundle_digest': plan['contract_digest'], 'adapter': 'json-state-v1',
              'baseline': {}, 'modified': {}}
    return root, bundle, plan, oracle, adapter_sha


def _native(root, source_sha, adapter_sha):
    identity = life._root_identity(root)
    return {'source_identity': {'device': identity['device'], 'inode': identity['inode']},
            'files': [{'path': 'host.py', 'sha256': source_sha},
                      {'path': 'adapter.py', 'sha256': adapter_sha}]}


def _apply(root, bundle, plan, oracle, adapter_sha, monkeypatch):
    monkeypatch.setattr(life, 'inspect_receipt', lambda *args, **kwargs: None)
    monkeypatch.setattr(life, 'inspect_baseline_postconditions',
                        lambda *args, **kwargs: {'postconditions_satisfied': True})
    baseline = _native(root, plan['source_sha256'], adapter_sha)
    receipt = {'scheduled': 1, 'exited_zero': 1}
    return life.apply_adaptation(root, bundle, plan['contract_digest'], baseline_spec=baseline,
                                 baseline_receipt=receipt, baseline_outputs={}, oracle=oracle,
                                 trusted_oracle_sha256='0'*64,
                                 trusted_baseline_receipt_sha256='1'*64)


def test_adaptation_plan_apply_verify_and_owned_rollback(tmp_path, monkeypatch):
    root, bundle, plan, oracle, adapter_sha = _fixture(tmp_path)
    assert life.adaptation_status(root, bundle)['status'] == 'planned'
    with pytest.raises(InputError, match='approved'):
        life.apply_adaptation(root, bundle, '0'*64, baseline_spec={}, baseline_receipt={},
                              baseline_outputs={}, oracle=oracle, trusted_oracle_sha256='0'*64,
                              trusted_baseline_receipt_sha256='1'*64)
    assert (root / 'host.py').read_bytes() == HOST.encode()
    assert _apply(root, bundle, plan, oracle, adapter_sha, monkeypatch)['status'] == 'applied_unverified'
    assert life.adaptation_status(root, bundle)['status'] == 'applied_unverified'
    monkeypatch.setattr(life, 'inspect_lifecycle_postconditions',
                        lambda *args, **kwargs: {'postconditions_satisfied': True})
    result = life.verify_adaptation(root, bundle,
        baseline_spec=_native(root, plan['source_sha256'], adapter_sha),
        baseline_receipt={}, baseline_outputs={},
        modified_spec=_native(root, plan['new_sha256'], adapter_sha),
        modified_receipt={'scheduled': 1, 'exited_zero': 1}, modified_outputs={},
        oracle=oracle, trusted_oracle_sha256='0'*64,
        trusted_baseline_receipt_sha256='1'*64, trusted_modified_receipt_sha256='2'*64)
    assert result['status'] == 'verified_fresh'
    assert life.adaptation_status(root, bundle)['status'] == 'applied_unverified'
    assert life.rollback_adaptation(root, bundle, plan['contract_digest'])['status'] == 'rolled_back'
    assert (root / 'host.py').read_bytes() == HOST.encode()


def test_interrupted_apply_blocks_status_and_restores_only_owned_bytes(tmp_path, monkeypatch):
    root, bundle, plan, oracle, adapter_sha = _fixture(tmp_path)
    def crash(root, patch, approval, *, progress):
        (Path(root) / 'host.py').write_bytes(patch['changes'][0]['new_content'].encode())
        raise RuntimeError('synthetic interruption after write')
    monkeypatch.setattr(life, 'apply_patch_plan', crash)
    with pytest.raises(RuntimeError, match='interruption'):
        _apply(root, bundle, plan, oracle, adapter_sha, monkeypatch)
    assert life.adaptation_status(root, bundle)['status'] == 'blocked_recovery'
    monkeypatch.undo()
    assert life.rollback_adaptation(root, bundle, plan['contract_digest'])['status'] == 'rolled_back'
    assert (root / 'host.py').read_bytes() == HOST.encode()


def test_adapter_drift_blocks_apply_and_source_drift_blocks_rollback(tmp_path, monkeypatch):
    root, bundle, plan, oracle, adapter_sha = _fixture(tmp_path)
    (root / 'adapter.py').write_text('changed\n')
    with pytest.raises(InputError, match='adapter'):
        life.adaptation_status(root, bundle)
    (root / 'adapter.py').write_bytes(ADAPTER.encode())
    _apply(root, bundle, plan, oracle, adapter_sha, monkeypatch)
    (root / 'host.py').write_text('unrelated edit\n')
    assert life.adaptation_status(root, bundle)['status'] == 'blocked_recovery'
    with pytest.raises(InputError, match='changed owned'):
        life.rollback_adaptation(root, bundle, plan['contract_digest'])
