"""The required-case check refuses skipped, missing and failed modules."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_required_cases',
                                              ROOT / 'scripts/check_required_cases.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

REPORT = '''<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="6" skipped="2" failures="1" errors="1">
<testcase classname="tests.test_ran" name="test_one"/>
<testcase classname="tests.test_ran" name="test_two"/>
<testcase classname="tests.test_skipped" name="test_gate"><skipped message="gate"/></testcase>
<testcase classname="tests.test_partly" name="test_ok"/>
<testcase classname="tests.test_partly" name="test_gate"><skipped message="gate"/></testcase>
<testcase classname="tests.test_failed" name="test_bad"><failure message="bad"/></testcase>
<testcase classname="tests.test_errored" name="test_setup"><error message="setup"/></testcase>
</testsuite></testsuites>
'''


@pytest.fixture
def report(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text(REPORT, encoding='utf-8')
    return path


def _run(tmp_path, report, modules):
    listing = tmp_path / 'modules.txt'
    listing.write_text('# required\n' + '\n'.join(modules) + '\n', encoding='utf-8')
    return checker.main(['--junit', str(report), '--modules-file', str(listing)])


def test_fully_executed_module_passes(tmp_path, report):
    assert _run(tmp_path, report, ['tests.test_ran']) == 0


@pytest.mark.parametrize('module', ['tests.test_skipped', 'tests.test_partly',
                                    'tests.test_failed', 'tests.test_errored',
                                    'tests.test_never_collected'])
def test_incomplete_required_module_fails(tmp_path, report, module):
    assert _run(tmp_path, report, ['tests.test_ran', module]) == 1
    assert len(checker.check(str(report), ['tests.test_ran', module])) == 1


def test_empty_or_duplicate_list_is_refused(tmp_path, report):
    assert _run(tmp_path, report, []) == 2
    assert _run(tmp_path, report, ['tests.test_ran', 'tests.test_ran']) == 2


def test_committed_list_names_existing_test_modules():
    listing = ROOT / '.github/required-installed-journeys.txt'
    modules = [line.strip() for line in listing.read_text(encoding='utf-8').splitlines()
               if line.strip() and not line.startswith('#')]
    assert modules and len(set(modules)) == len(modules)
    for module in modules:
        assert module.startswith('tests.')
        assert (ROOT / (module.replace('.', '/') + '.py')).is_file(), module
