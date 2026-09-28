"""Central discovery commands preserve private, non-authoritative artifacts."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities, cli


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def host(tmp_path):
    if os.name != 'posix':
        pytest.skip('This legacy fixture asserts POSIX descriptor and 0600 mode behavior')
    root = tmp_path / 'private-target'
    root.mkdir()
    (root / 'opaque.py').write_text(
        'raise RuntimeError("TARGET MUST NOT EXECUTE")\n\n'
        'def n4(p):\n    return p.dispatch()\n\n'
        'def v8(p):\n    return n4(p)\n', encoding='utf-8')
    return root


def nomination(report):
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol'] == 'v8')
    source = deepcopy(seam['source'])
    return {'schema_version': '1.0', 'discovery_version': capabilities.VERSION,
            'report_sha256': report['report_sha256'], 'seam_id': seam['seam_id'],
            'source': source, 'pattern': 'C', 'proposer': 'synthetic-cli-test',
            'rationale': 'Finite dispatch hypothesis requiring separate semantic review.',
            'evidence': [{k: source[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}]}


def test_central_help_exposes_discovery_without_implementation_claims():
    help_text = cli.parser().format_help()
    assert 'discover-capabilities' in help_text and 'nominate-candidate' in help_text
    assert 'semantic and binding review remain pending' in ' '.join(help_text.split())


def test_central_discovery_and_nomination_keep_private_pending_artifacts(host, tmp_path, capsys, monkeypatch):
    def forbidden_config(*args, **kwargs):
        raise AssertionError('Discovery must use its external policy, not generic configuration')
    monkeypatch.setattr(cli, 'load_config', forbidden_config)
    original = (host / 'opaque.py').read_bytes()
    report_path = tmp_path / 'capabilities.json'
    assert cli.main(['discover-capabilities', '--repo', str(host), '--out', str(report_path)]) == 0
    report = json.loads(report_path.read_text())
    output = capsys.readouterr()
    assert json.loads(output.out) == {'status': 'written', 'artifact_sha256': capabilities._digest(report)}
    assert str(host) not in output.out + output.err
    assert report['discovery_outcome'] == 'review_required'
    assert os.stat(report_path).st_mode & 0o777 == 0o600
    proposal_path = tmp_path / 'nomination.json'
    proposal_path.write_text(json.dumps(nomination(report)), encoding='utf-8')
    admitted_path = tmp_path / 'admitted.json'
    assert cli.main(['nominate-candidate', '--repo', str(host), '--nomination', str(proposal_path),
                     '--report-sha256', report['report_sha256'], '--out', str(admitted_path)]) == 0
    admitted = json.loads(admitted_path.read_text())
    output = capsys.readouterr()
    assert json.loads(output.out)['artifact_sha256'] == capabilities._digest(admitted)
    assert str(host) not in output.out + output.err
    assert admitted['semantic_review'] == 'not_performed'
    assert admitted['status'] == 'nominated_pending_semantic_and_binding_review'
    assert not admitted['execution_qualified'] and not any(admitted['authorization'].values())
    assert os.stat(admitted_path).st_mode & 0o777 == 0o600
    assert (host / 'opaque.py').read_bytes() == original


def test_central_discovery_cannot_overwrite_or_write_inside_target(host, tmp_path, capsys):
    output = tmp_path / 'report.json'
    args = ['discover-capabilities', '--repo', str(host), '--out', str(output)]
    assert cli.main(args) == 0
    original = output.read_bytes()
    capsys.readouterr()
    assert cli.main(args) == 2
    assert output.read_bytes() == original
    assert json.loads(capsys.readouterr().err)['reason'] == 'output_unavailable_or_exists'
    assert cli.main(['discover-capabilities', '--repo', str(host), '--out', str(host / 'report.json')]) == 2
    assert not (host / 'report.json').exists()
    assert json.loads(capsys.readouterr().err)['reason'] == 'output_must_be_outside_repository'


def test_central_nomination_rejects_stale_source(host, tmp_path, capsys):
    report = capabilities.discover_repository(host)
    path = tmp_path / 'nomination.json'
    path.write_text(json.dumps(nomination(report)), encoding='utf-8')
    with (host / 'opaque.py').open('a', encoding='utf-8') as target:
        target.write('\n# source changed\n')
    output = tmp_path / 'admitted.json'
    assert cli.main(['nominate-candidate', '--repo', str(host), '--nomination', str(path),
                     '--report-sha256', report['report_sha256'], '--out', str(output)]) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert json.loads(captured.err)['reason'] == 'stale_report_or_policy'
    assert str(host) not in captured.out + captured.err


def test_central_policy_remains_external_and_applies_to_nomination(host, tmp_path, capsys):
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'hard_real_time': ['opaque.py::v8']}), encoding='utf-8')
    output = tmp_path / 'report.json'
    assert cli.main(['discover-capabilities', '--repo', str(host), '--policy', str(policy), '--out', str(output)]) == 0
    report = json.loads(output.read_text())
    proposed = tmp_path / 'nomination.json'
    proposed.write_text(json.dumps(nomination(report)), encoding='utf-8')
    capsys.readouterr()
    assert cli.main(['nominate-candidate', '--repo', str(host), '--policy', str(policy),
                     '--nomination', str(proposed), '--report-sha256', report['report_sha256'],
                     '--out', str(tmp_path / 'admitted.json')]) == 2
    assert json.loads(capsys.readouterr().err)['reason'] == 'hard_real_time_exclusion'
    internal = host / 'policy.json'
    internal.write_text('{}', encoding='utf-8')
    assert cli.main(['discover-capabilities', '--repo', str(host), '--policy', str(internal),
                     '--out', str(tmp_path / 'other.json')]) == 2
    assert json.loads(capsys.readouterr().err)['reason'] == 'policy_must_be_external'


@pytest.mark.parametrize('name,kind', [
    ('report', 'repository-capabilities'), ('nomination', 'candidate-nomination'), ('admitted', 'admitted-nomination'),
])
def test_validate_capability_contracts_has_explicit_structural_scope(name, kind, tmp_path, capsys):
    value = json.loads((ROOT / 'examples/capabilities' / (name + '.example.json')).read_text())
    path = tmp_path / 'artifact.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    command = ['validate', '--kind', kind, '--input', str(path)]
    assert cli.main(command) == 0
    assert json.loads(capsys.readouterr().out) == {
        'status': 'valid', 'kind': kind, 'records': 1, 'source_revalidated': False,
    }
    value['unreviewed'] = 'PRIVATE_SENTINEL'
    path.write_text(json.dumps(value), encoding='utf-8')
    assert cli.main(command) == 2
    captured = capsys.readouterr()
    assert 'PRIVATE_SENTINEL' not in captured.out + captured.err


@pytest.mark.parametrize('text', ['{"PRIVATE_SENTINEL":0,"PRIVATE_SENTINEL":1}', '{"x":NaN}', '[' * 2000])
def test_validate_capability_input_errors_do_not_echo_private_data(text, tmp_path, capsys):
    path = tmp_path / 'private-input.json'
    path.write_text(text, encoding='utf-8')
    assert cli.main(['validate', '--kind', 'candidate-nomination', '--input', str(path)]) == 2
    captured = capsys.readouterr()
    assert 'PRIVATE_SENTINEL' not in captured.out + captured.err
    assert str(path) not in captured.out + captured.err


def test_validate_report_rejects_changed_content_digest(tmp_path, capsys):
    value = json.loads((ROOT / 'examples/capabilities/report.example.json').read_text())
    value['report_sha256'] = '0' * 64
    path = tmp_path / 'report.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    assert cli.main(['validate', '--kind', 'repository-capabilities', '--input', str(path)]) == 2
    assert json.loads(capsys.readouterr().err)['message'] == 'Capability report digest mismatch'


def test_validate_accepts_report_larger_than_nomination_input_limit(host, tmp_path, capsys):
    with (host / 'opaque.py').open('a', encoding='utf-8') as target:
        for index in range(700):
            target.write(f'\ndef opaque_{index}(p):\n    return n4(p)\n')
    report = capabilities.discover_repository(host)
    raw = capabilities._json(report) + b'\n'
    assert len(raw) > capabilities.MAX_INPUT_BYTES
    path = tmp_path / 'large-report.json'
    path.write_bytes(raw)
    assert cli.main(['validate', '--kind', 'repository-capabilities', '--input', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['source_revalidated'] is False


@pytest.mark.parametrize('name,kind', [
    ('report', 'repository-capabilities'), ('nomination', 'candidate-nomination'), ('admitted', 'admitted-nomination'),
])
def test_validate_capability_contract_examples_are_read_without_platform_restriction(name, kind, tmp_path, capsys):
    path = tmp_path / 'artifact.json'
    path.write_bytes((ROOT / 'examples/capabilities' / (name + '.example.json')).read_bytes())
    assert cli.main(['validate', '--kind', kind, '--input', str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        'status': 'valid', 'kind': kind, 'records': 1, 'source_revalidated': False}


def test_central_discovery_reports_unsupported_secure_filesystem(tmp_path, capsys, monkeypatch):
    def unavailable(*args, **kwargs):
        raise capabilities.CapabilityError('unsupported_secure_filesystem')
    monkeypatch.setattr(capabilities, '_secure_discovery_root', unavailable)
    assert cli.main(['discover-capabilities', '--repo', str(tmp_path),
                     '--out', str(tmp_path.parent / 'not-written.json')]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {'status': 'blocked', 'reason': 'unsupported_secure_filesystem'}
    assert str(tmp_path) not in captured.out + captured.err
