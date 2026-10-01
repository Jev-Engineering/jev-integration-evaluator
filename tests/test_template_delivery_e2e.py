"""Registered-tool qualification report driver: statuses come only from JUnit (issue 57).

These are ungated unit tests of the report driver with synthetic JUnit files.
They do not run an installed journey and are not qualification evidence.
"""
import json
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.registered_tool_qualification import (
    AUTHENTIC_GATES, GATES, KIND, PENDING_STATUS, main,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'registered-tool-qualification-report-v1.schema.json'
OFFLINE = [gate for gate in GATES if gate['kind'] == 'offline']
MODULES = sorted({module for gate in GATES for module in gate['required_modules']})


def _dotted(module):
    return module.removesuffix('.py').replace('/', '.')


def _case(classname, name, outcome='passed'):
    child = {'passed': '', 'skipped': '<skipped message="opt-in input absent"/>',
             'failed': '<failure message="assertion"/>', 'error': '<error message="setup"/>'}[outcome]
    return f'<testcase classname={quoteattr(classname)} name={quoteattr(name)} time="0.01">{child}</testcase>'


def _junit(path, cases):
    path.write_bytes(('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
                      + ''.join(cases) + '</testsuite></testsuites>\n').encode('utf-8'))
    return path


def _all_passed(overrides=None, omit=()):
    cases = []
    for module in MODULES:
        if module in omit:
            continue
        for name in ('test_one', 'test_two[param]'):
            cases.append(_case(_dotted(module), name, (overrides or {}).get((module, name), 'passed')))
    return cases


def _run(tmp_path, cases, *extra, name='report.json'):
    junit = _junit(tmp_path / 'junit.xml', cases)
    out = tmp_path / name
    code = main(['--junit', str(junit), '--out', str(out), *extra])
    return code, out


def _gates(out):
    report = json.loads(out.read_text(encoding='utf-8'))
    validate_contract(report, KIND)
    return report, {gate['id']: gate for gate in report['gates']}


def _owners(module):
    return [gate['id'] for gate in OFFLINE if module in gate['required_modules']]


def test_all_offline_modules_passed_leaves_authentic_gates_pending(tmp_path, capsys):
    code, out = _run(tmp_path, _all_passed(), '--require-offline-complete')
    assert code == 0
    report, gates = _gates(out)
    assert [gate['id'] for gate in report['gates']] == [gate['id'] for gate in GATES]
    assert all(gates[gate['id']]['status'] == 'passed' for gate in OFFLINE)
    assert all(gates[name]['status'] == PENDING_STATUS for name in AUTHENTIC_GATES)
    summary = report['summary']
    assert summary['gate_count'] == len(GATES)
    assert summary['offline_gate_count'] == summary['passed'] == len(OFFLINE)
    assert summary['failed'] == summary['unrun'] == 0
    assert summary['pending_gates'] == list(AUTHENTIC_GATES)
    assert summary['pending_authentic_evidence'] == len(AUTHENTIC_GATES)
    assert summary['offline_complete'] is True and summary['qualification_complete'] is False
    assert (report['target_code_executed'], report['network_requests']) == (False, 0)
    assert report['provider_qualification'] == 'not_run' and report['observed_benefit'] is False
    assert report['junit']['testcases'] == report['junit']['passed'] == 2 * len(MODULES)
    assert b'\r' not in out.read_bytes()
    printed = json.loads(capsys.readouterr().out)
    assert printed['status'] == 'report_written' and printed['qualification_complete'] is False


def test_skipped_module_is_unrun_and_blocks_offline_complete(tmp_path, capsys):
    module = 'tests/test_template_installation.py'
    cases = _all_passed(omit=(module,)) + [_case('', _dotted(module), 'skipped')]
    code, out = _run(tmp_path, cases)
    assert code == 0
    report, gates = _gates(out)
    assert gates['package_install']['status'] == 'unrun'
    assert gates['package_install']['modules'] == [
        {'module': module, 'cases': 1, 'passed': 0, 'failed': 0, 'skipped': 1}]
    assert report['summary']['unrun_gates'] == _owners(module) == ['package_install']
    assert report['summary']['unrun'] == 1 and report['summary']['offline_complete'] is False
    assert report['summary']['passed'] == len(OFFLINE) - 1
    assert report['summary']['gate_count'] == len(GATES)
    strict, _ = _run(tmp_path, cases, '--require-offline-complete', name='strict.json')
    assert strict == 3 and (tmp_path / 'strict.json').is_file()
    capsys.readouterr()


def test_one_skipped_case_among_passes_is_unrun(tmp_path, capsys):
    module = 'tests/test_registered_alpha_installed_upgrade.py'
    code, out = _run(tmp_path, _all_passed({(module, 'test_two[param]'): 'skipped'}))
    report, gates = _gates(out)
    assert code == 0 and gates['installed_upgrade_rollback']['status'] == 'unrun'
    assert report['summary']['unrun_gates'] == ['installed_upgrade_rollback']
    capsys.readouterr()


@pytest.mark.parametrize('outcome', ['failed', 'error'])
def test_failed_case_fails_every_gate_that_requires_the_module(tmp_path, capsys, outcome):
    module = 'tests/test_template_delivery_installed.py'
    # A skip in the same gate must not hide the failure.
    cases = _all_passed({(module, 'test_one'): outcome,
                         ('tests/test_template_delivery_session.py', 'test_one'): 'skipped'})
    code, out = _run(tmp_path, cases)
    assert code == 0
    report, gates = _gates(out)
    assert gates['delivery_session_off']['status'] == 'failed'
    assert report['summary']['failed_gates'] == _owners(module) == ['delivery_session_off']
    assert report['summary']['failed'] == 1 and report['junit']['failed'] == 1
    assert report['summary']['offline_complete'] is False
    strict, _ = _run(tmp_path, cases, '--require-offline-complete', name='strict.json')
    assert strict == 3
    capsys.readouterr()


def test_absent_module_is_unrun_not_passed(tmp_path, capsys):
    module = 'tests/test_work_queue_installed.py'
    code, out = _run(tmp_path, _all_passed(omit=(module,)))
    report, gates = _gates(out)
    assert code == 0 and gates['second_independent_host']['status'] == 'unrun'
    row = {item['module']: item for item in gates['second_independent_host']['modules']}
    assert row[module]['cases'] == 0
    assert row['tests/test_work_queue_oracle.py']['passed'] == 2
    assert report['summary']['unrun_gates'] == ['second_independent_host']
    capsys.readouterr()


def test_empty_junit_leaves_every_offline_gate_unrun(tmp_path, capsys):
    code, out = _run(tmp_path, [])
    report, gates = _gates(out)
    assert code == 0
    assert report['summary']['unrun_gates'] == [gate['id'] for gate in OFFLINE]
    assert report['summary']['passed'] == 0
    assert report['summary']['pending_gates'] == list(AUTHENTIC_GATES)
    capsys.readouterr()


def test_similarly_named_modules_and_cases_do_not_count(tmp_path, capsys):
    cases = [_case('tests.test_template_catalog_extra', 'test_one'),
             _case('other.tests.test_template_catalog', 'test_one'),
             _case('test_template_catalog', 'test_one'),
             _case('', 'tests.test_template_catalog_extra')]
    code, out = _run(tmp_path, cases)
    _, gates = _gates(out)
    assert code == 0 and gates['template_materialize']['status'] == 'unrun'
    assert gates['template_materialize']['modules'][0]['cases'] == 0
    nested = [_case('tests.test_template_catalog.TestGroup', 'test_one')]
    code, out = _run(tmp_path, nested, name='nested.json')
    assert _gates(out)[1]['template_materialize']['status'] == 'passed'
    capsys.readouterr()


def test_authentic_gates_are_never_promoted_by_matching_cases(tmp_path, capsys):
    cases = _all_passed()
    for gate_id in AUTHENTIC_GATES:
        cases += [_case('tests.test_' + gate_id, 'test_' + gate_id),
                  _case(gate_id, gate_id), _case('', gate_id),
                  _case('tests.test_template_delivery_e2e', 'test_' + gate_id + '_passed')]
    code, out = _run(tmp_path, cases, '--require-offline-complete')
    assert code == 0
    report, gates = _gates(out)
    for gate_id in AUTHENTIC_GATES:
        assert gates[gate_id]['status'] == PENDING_STATUS
        assert gates[gate_id]['modules'] == [] and gates[gate_id]['required_modules'] == []
        assert gate_id not in report['summary']['passed_gates']
    assert report['summary']['passed'] == len(OFFLINE) < report['summary']['gate_count']
    assert report['summary']['qualification_complete'] is False
    capsys.readouterr()


def test_schema_refuses_a_promoted_or_dropped_authentic_gate(tmp_path, capsys):
    _, out = _run(tmp_path, _all_passed())
    report, _ = _gates(out)
    capsys.readouterr()
    promoted = json.loads(json.dumps(report))
    next(gate for gate in promoted['gates'] if gate['id'] == 'authorized_canary')['status'] = 'passed'
    dropped = json.loads(json.dumps(report))
    dropped['gates'] = [gate for gate in dropped['gates'] if gate['id'] != 'authorized_canary']
    complete = json.loads(json.dumps(report))
    complete['summary']['qualification_complete'] = True
    extra = json.loads(json.dumps(report))
    extra['approved'] = True
    for invalid in (promoted, dropped, complete, extra):
        with pytest.raises(Exception, match='Invalid ' + KIND):
            validate_contract(invalid, KIND)


def test_refuses_output_inside_the_checkout(tmp_path, capsys):
    junit = _junit(tmp_path / 'junit.xml', _all_passed())
    for inside in (ROOT / 'qualification-report-must-not-exist.json',
                   ROOT / 'reports' / 'qualification-report-must-not-exist.json'):
        assert main(['--junit', str(junit), '--out', str(inside)]) == 2
        assert not inside.exists()
        assert json.loads(capsys.readouterr().err) == {
            'schema_version': '1.0', 'status': 'rejected',
            'reason': 'report_must_be_outside_the_checkout'}


def test_refuses_existing_output_and_missing_parent(tmp_path, capsys):
    junit = _junit(tmp_path / 'junit.xml', _all_passed())
    existing = tmp_path / 'existing.json'
    existing.write_bytes(b'retained\n')
    assert main(['--junit', str(junit), '--out', str(existing)]) == 2
    assert existing.read_bytes() == b'retained\n'
    assert json.loads(capsys.readouterr().err)['reason'] == 'report_output_already_exists'
    assert main(['--junit', str(junit), '--out', str(tmp_path / 'absent' / 'report.json')]) == 2
    assert json.loads(capsys.readouterr().err)['reason'] == 'report_parent_directory_required'
    assert not (tmp_path / 'absent').exists()


@pytest.mark.parametrize('raw, reason', [
    (b'<testsuites><testsuite>', 'junit_report_malformed'),
    (b'<report/>', 'junit_report_malformed'),
    (b'<!DOCTYPE x [<!ENTITY a "b">]><testsuites/>', 'junit_report_declares_unsupported_markup'),
    (None, 'junit_report_unavailable_or_oversize'),
])
def test_refuses_unusable_junit_without_writing(tmp_path, capsys, raw, reason):
    junit = tmp_path / 'junit.xml'
    if raw is not None:
        junit.write_bytes(raw)
    out = tmp_path / 'report.json'
    assert main(['--junit', str(junit), '--out', str(out), '--require-offline-complete']) == 2
    assert json.loads(capsys.readouterr().err)['reason'] == reason
    assert not out.exists()


def test_script_entrypoint_exit_codes_and_identical_reports(tmp_path):
    passed = _junit(tmp_path / 'passed.xml', _all_passed())
    partial = _junit(tmp_path / 'partial.xml', _all_passed(omit=('tests/test_template_catalog.py',)))
    script = str(ROOT / 'scripts' / 'run_registered_tool_qualification.py')

    def run(junit, name, *extra):
        return subprocess.run([sys.executable, script, '--junit', str(junit),
                               '--out', str(tmp_path / name), *extra],
                              cwd=tmp_path, capture_output=True, text=True, timeout=60)

    assert run(passed, 'a.json', '--require-offline-complete').returncode == 0
    assert run(passed, 'b.json').returncode == 0
    assert (tmp_path / 'a.json').read_bytes() == (tmp_path / 'b.json').read_bytes()
    assert run(partial, 'c.json').returncode == 0
    strict = run(partial, 'd.json', '--require-offline-complete')
    assert strict.returncode == 3
    assert json.loads(strict.stdout)['unrun'] == 1
    assert json.loads((tmp_path / 'd.json').read_text(encoding='utf-8'))['summary']['unrun_gates'] == [
        'template_materialize']
    again = run(partial, 'd.json')
    assert again.returncode == 2 and 'report_output_already_exists' in again.stderr


def test_schema_copies_are_identical_and_gate_modules_exist():
    public = (ROOT / 'schemas' / SCHEMA).read_bytes()
    assert public == (ROOT / 'jev_integration_evaluator' / 'data' / SCHEMA).read_bytes()
    assert b'\r' not in public
    for module in MODULES:
        assert (ROOT / module).is_file(), module
    source = (ROOT / 'jev_integration_evaluator' / 'registered_tool_qualification.py').read_text(
        encoding='utf-8')
    for forbidden in ('subprocess', 'socket', 'urllib', 'http.client', 'importlib', 'jsonschema'):
        assert forbidden not in source
