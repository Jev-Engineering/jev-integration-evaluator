from __future__ import annotations
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from jev_integration_evaluator.runners import isolated_python as runner
from jev_integration_evaluator.runners.observations import _observation

ROOT = Path(__file__).resolve().parents[1]


def contract():
    zero = '0' * 64
    identity = {key: zero if key.endswith('_sha256') else 'qualified'
                for key in ('python_executable', 'python_sha256', 'python_version',
                            'machine', 'kernel', 'worker_sha256', 'supervisor_sha256',
                            'library_path', 'library_sha256',
                            'runtime_dependencies_sha256')}
    file = {'path': 'entry.py', 'sha256': zero, 'bytes': 0, 'mode': 0o644}
    return {
        'schema_version': '1.1', 'backend': runner.BACKEND,
        'isolation_capabilities': dict(runner.ISOLATION_CAPABILITIES),
        'source_identity': {'device': 1, 'inode': 1}, 'files': [file],
        'environment_identity': identity, 'environment': {},
        'schedule': [{'case_id': 'off', 'entry': 'entry.py', 'argv': []}],
        'limits': {'wall_seconds': 3, 'cpu_seconds': 2,
                   'address_space_bytes': 128 * 1024**2, 'open_files': 32,
                   'output_bytes': 4096, 'schedule_seconds': 30},
        'target_environment': {
            'interpreter_path': '/approved/python', 'interpreter_sha256': zero,
            'dependency_root': '/approved/site-packages',
            'dependency_identity': {'device': 2, 'inode': 2},
            'files': [
                {'path': 'toy_package/__init__.py', 'sha256': zero, 'bytes': 0, 'mode': 0o644},
                {'path': 'toy_package-1.0.dist-info/METADATA', 'sha256': zero,
                 'bytes': 0, 'mode': 0o644},
            ],
            'distributions': [{'name': 'toy_package', 'version': '1.0',
                               'metadata_path': 'toy_package-1.0.dist-info/METADATA'}],
        },
    }


def test_versioned_target_contract_and_mirrors_are_strict():
    spec = contract()
    runner.validate_spec(spec)
    left = json.loads((ROOT / 'schemas/native-runner-spec-v1.schema.json').read_text())
    right = json.loads((ROOT / 'jev_integration_evaluator/data/native-runner-spec-v1.schema.json').read_text())
    assert left == right
    for name in ('native-postconditions-v1', 'native-postcondition-report-v1',
                 'native-private-output-v1'):
        assert json.loads((ROOT / 'schemas' / (name + '.schema.json')).read_text()) == json.loads(
            (ROOT / 'jev_integration_evaluator/data' / (name + '.schema.json')).read_text())
    jsonschema.validate(spec, left)
    bad = copy.deepcopy(spec)
    bad['target_environment']['files'].append(
        {'path': 'toy_package/native.so', 'sha256': '0' * 64, 'bytes': 0, 'mode': 0o644})
    with pytest.raises(runner.RunnerError, match='unsupported_or_duplicate_dependency'):
        runner.validate_spec(bad)


def test_unproven_dependency_module_rejected_without_target_execution():
    spec = contract()
    spec['target_environment']['files'][0]['path'] = 'other_package/__init__.py'
    with pytest.raises(runner.RunnerError, match='unproven_dependency_module'):
        runner.validate_spec(spec)


def test_isolation_capabilities_are_code_owned():
    spec = contract()
    spec['isolation_capabilities']['network'] = 'allowed'
    with pytest.raises(runner.RunnerError, match='unsupported_isolation_capabilities'):
        runner.validate_spec(spec)


def test_native_artifact_in_host_snapshot_is_rejected():
    spec = contract()
    spec['files'].append({'path': 'extensions/unsafe.so.1', 'sha256': '0' * 64,
                          'bytes': 0, 'mode': 0o644})
    with pytest.raises(runner.RunnerError, match='unsupported_native_artifact'):
        runner.validate_spec(spec)


@pytest.mark.parametrize('payload', [
    b'{"reached":true,"reached":false}\n',
    b'{"reached":NaN}\n',
    b'{}\n{}\n',
])
def test_native_observation_rejects_ambiguous_or_malformed_json(payload):
    with pytest.raises(runner.RunnerError, match='invalid_native_observation'):
        _observation(payload)
