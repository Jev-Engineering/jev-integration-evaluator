"""The hosted Windows delivery job schedules every native delivery file in exactly one shard.

This reads the workflow text and collects test identifiers only; it runs no
native case, so it holds on every platform.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
# The files of the unsharded job, plus later additions. Each must stay in one shard.
REQUIRED = (
    'tests/test_windows_template_preflight.py',
    'tests/test_windows_template_package_inputs.py',
    'tests/test_windows_template_owned.py',
    'tests/test_windows_template_session.py',
    'tests/test_windows_template_delivery.py',
    'tests/test_windows_template_run.py',
    'tests/test_windows_template_install_faults.py',
    'tests/test_windows_template_install_death.py',
    'tests/test_windows_source_mutation.py',
    'tests/test_windows_source_read_refusal.py',
)
_FILE = re.compile(r'tests/\w+\.py')


def _jobs() -> dict:
    return yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))['jobs']


def _shards() -> list:
    return _jobs()['windows-template-delivery']['strategy']['matrix']['shard']


def _runs(job: dict) -> str:
    return '\n'.join(step.get('run', '') for step in job['steps'])


def test_every_native_delivery_file_is_in_exactly_one_shard():
    shards = _shards()
    assert len(shards) >= 2
    assert len({shard['name'] for shard in shards}) == len(shards)
    scheduled = Counter()
    for shard in shards:
        files = shard['files'].split()
        # A shard lists whole test files only; no option or selector hides in it.
        assert files and all(_FILE.fullmatch(name) for name in files)
        scheduled.update(files)
    assert all((ROOT / name).is_file() for name in scheduled)
    assert {name: count for name, count in scheduled.items() if count != 1} == {}
    # The connected job owns its own files; a file is never scheduled twice.
    connected = set(_FILE.findall(_runs(_jobs()['windows-connected-shadow'])))
    assert not connected & set(scheduled)
    native = {path.relative_to(ROOT).as_posix()
              for pattern in ('test_windows_template_*.py', 'test_windows_source_*.py')
              for path in (ROOT / 'tests').glob(pattern)}
    missing = sorted((native | set(REQUIRED)) - connected - set(scheduled))
    assert missing == [], 'add each file to one windows-template-delivery shard'


def test_each_shard_keeps_environment_filter_and_skip_rejection():
    job = _jobs()['windows-template-delivery']
    assert job['runs-on'] == 'windows-2022' and job['timeout-minutes'] <= 90
    assert job['name'].startswith('windows-template-delivery')
    assert job['strategy']['matrix']['python'] == ['3.10', '3.13', '3.14']
    # Every step is unconditional, so each shard prepares the same environment.
    assert not any('if' in step for step in job['steps'])
    text = _runs(job)
    for required in ('AllowDevelopmentWithoutDevLicense', 'LongPathsEnabled',
                     'scripts/prepare_template_wheelhouse.py',
                     'JEV_WINDOWS_TEMPLATE_WHEELHOUSE=',
                     'python -m pytest -q ${{ matrix.shard.files }} -k "not non_windows"',
                     'sys.exit(1 if n < ${{ matrix.shard.minimum }} or k or f else 0)',
                     'python scripts/validate_package.py --check-manifest'):
        assert text.count(required) == 1, required
    assert "int(x.get('skipped',0))" in text and "int(x.get('errors',0))" in text


@pytest.mark.parametrize('index', range(len(_shards())))
def test_shard_minimum_is_the_exact_collected_count(index):
    shard = _shards()[index]
    listed = subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider',
         *shard['files'].split(), '-k', 'not non_windows'],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert listed.returncode == 0, listed.stdout[-2000:]
    summary = re.search(r'^(\d+)(?:/\d+)? tests? collected', listed.stdout, re.MULTILINE)
    assert summary is not None, listed.stdout[-2000:]
    assert type(shard['minimum']) is int and int(summary.group(1)) == shard['minimum']
