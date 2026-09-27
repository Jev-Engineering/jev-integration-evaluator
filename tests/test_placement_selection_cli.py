"""Subprocess CLI tests. Test-created fixtures and approvals are synthetic only."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from jev_integration_evaluator.io import digest
from jev_integration_evaluator.selection import request_sha256, selection_engine_sha256
from scripts.implementation_fixtures import fixture


@pytest.fixture
def envelope(tmp_path):
    host = tmp_path/'host'
    inventory, spec = fixture(host, 'C', tag='cli_selection')
    request = {'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(), 'mode': 'experimental', 'inventory_sha256': digest(inventory),
        'candidate_id': spec['candidate_id'], 'decision_review': {'reviewer': 'synthetic-cli-review',
        'reason': 'DO_NOT_ECHO_REVIEW_SENTINEL: synthetic only', 'evidence_refs': ['fixture:cli']},
        'preparation_scope_ref': 'DO_NOT_ECHO_SCOPE_SENTINEL', 'implementation_spec_sha256': digest(spec),
        'constraints': None, 'live_limits': {'max_total_cost': None, 'max_total_calls': None,
                                            'max_concurrent_calls': None}}
    return host, {'schema_version': '1.0', 'inventory': inventory, 'request': request, 'specification': None}, spec


def invoke(data, *args, thin=False):
    root = Path(__file__).resolve().parents[1]
    entry = [str(root/'scripts/select_placement.py')] if thin else ['-m', 'jev_integration_evaluator.selection']
    return subprocess.run([sys.executable, *entry, *map(str, args)], input=data,
                          cwd=root, capture_output=True, timeout=30)


@pytest.mark.parametrize('thin', [False, True])
def test_no_approval_prepares_nothing_and_does_not_echo_sensitive_fields(envelope, tmp_path, thin):
    host, data, _ = envelope
    before = {p.name: p.read_bytes() for p in host.iterdir()}
    run = invoke(json.dumps(data).encode(), thin=thin)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result['selection_status'] == 'selection_review_required'
    assert result['implementation_status'] == 'not_prepared'
    assert result['target_modified'] is result['target_executed'] is False
    assert b'DO_NOT_ECHO_' not in run.stdout + run.stderr
    assert str(host).encode() not in run.stdout + run.stderr
    assert before == {p.name: p.read_bytes() for p in host.iterdir()}


@pytest.mark.parametrize('thin', [False, True])
def test_cli_prepares_real_bundle_but_never_applies(envelope, tmp_path, thin):
    host, data, spec = envelope
    data['specification'] = spec
    before = {p.name: p.read_bytes() for p in host.iterdir()}
    run = invoke(json.dumps(data).encode(), '--prepare', '--repo', host, '--bundle', tmp_path/'bundle',
                 '--approve-request', request_sha256(data['request']), thin=thin)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result['selection_status'] == 'experimental_selected'
    assert result['implementation_status'] == 'planned'
    assert (tmp_path/'bundle'/'implementation.diff').is_file()
    assert not (tmp_path/'bundle'/'baseline-receipt.json').exists()
    assert result['live_spend_authorized'] is result['runtime_activation_authorized'] is False
    assert b'DO_NOT_ECHO_' not in run.stdout + run.stderr
    assert before == {p.name: p.read_bytes() for p in host.iterdir()}


@pytest.mark.parametrize('payload', [b'', b'[]', b'{"x":1,"x":2}', b'NaN', b'\xff',
                                    b'{"schema_version":"1.0"}'])
def test_bad_envelope_redacted(payload):
    run = invoke(payload)
    assert run.returncode == 2
    assert json.loads(run.stderr)['error'] == 'invalid_selection_envelope'
    assert not run.stdout
    assert b'Traceback' not in run.stderr


@pytest.mark.parametrize('args', [['--prepare'], ['--repo', 'PRIVATE_PATH_SENTINEL'],
                                  ['--approve-request', 'PRIVATE_APPROVAL_SENTINEL'],
                                  ['--unrecognized', 'PRIVATE_ARGUMENT_SENTINEL']])
def test_invalid_arguments_do_not_echo_argv(args):
    run = invoke(b'', *args)
    assert run.returncode == 2
    assert b'PRIVATE_' not in run.stdout + run.stderr
    assert b'Traceback' not in run.stderr


def test_agent_envelope_cannot_supply_approval(envelope):
    _, data, _ = envelope
    data['approve_request'] = request_sha256(data['request'])
    run = invoke(json.dumps(data).encode())
    assert run.returncode == 2
    assert json.loads(run.stderr)['error'] == 'invalid_selection_envelope'


def test_spec_is_not_silently_ignored_without_prepare(envelope):
    _, data, spec = envelope; data['specification'] = spec
    run = invoke(json.dumps(data).encode())
    assert run.returncode == 2
    assert json.loads(run.stderr)['error'] == 'unexpected_specification_without_preparation'


def test_wrong_approval_no_output(envelope, tmp_path):
    host, data, spec = envelope; data['specification'] = spec
    run = invoke(json.dumps(data).encode(), '--prepare', '--repo', host, '--bundle', tmp_path/'bundle',
                 '--approve-request', '0'*64)
    assert run.returncode == 2
    assert json.loads(run.stderr)['error'] == 'selection_approval_mismatch'
    assert not (tmp_path/'bundle').exists()
