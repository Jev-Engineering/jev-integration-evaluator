import importlib.util
from pathlib import Path
import pytest
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.io import read_json, write_json, InputError


def demo_runner(root):
    spec = importlib.util.spec_from_file_location('jev_v11_demo', root / 'scripts/run_v11_demo.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.run_demo


def test_all_v11_cli_workflows_offline(root, tmp_path):
    result = demo_runner(root)(tmp_path / 'demo')
    assert result['network_requests'] == 0 and result['host_actions_executed'] == 0
    assert result['holdout_observations'] == 120 and result['task_pairs'] == 80
    assert result['study_recommendation'] == 'needs_more_evidence'
    assert result['holdout_eligible_for_activation'] is False
    assert result['threshold_enforcement_exit'] == 3
    assert len(result['commands']) == 19
    diff = read_json(tmp_path / 'demo/snapshot-diff.json')
    assert diff['configuration_changed']
    assert (tmp_path / 'demo/snapshot-diff.report.md').exists()
    assert 'synthetic' in (tmp_path / 'demo/holdout-report.report.md').read_text()


def test_demo_does_not_overwrite_existing_files(root, tmp_path):
    (tmp_path / 'important.txt').write_text('preserve')
    with pytest.raises(InputError): demo_runner(root)(tmp_path)
    assert (tmp_path / 'important.txt').read_text() == 'preserve'


def test_cli_robustness_does_not_assume_network_authority(tmp_path):
    assert main(['robustness-run', '--plan', str(tmp_path / 'absent.json'), '--out', str(tmp_path / 'out.json')]) == 2
    assert not (tmp_path / 'out.json').exists()


def test_new_schema_errors_do_not_print_payload(tmp_path, capsys):
    write_json(tmp_path / 'input.json', {'sensitive': 'SECRET_UNITTEST_PAYLOAD'})
    assert main(['validate', '--kind', 'holdout-report', '--input', str(tmp_path / 'input.json')]) == 2
    assert 'SECRET_UNITTEST_PAYLOAD' not in capsys.readouterr().err
