"""Installed-wheel JS/TS owned lifecycle through the public CLI, offline."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_js_lifecycle import fixture as host_fixture

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / 'node_modules/typescript/lib/typescript.js'
pytestmark = pytest.mark.skipif(os.name != 'posix' or shutil.which('node') is None or not PINNED.is_file(),
                                reason='Native POSIX and pinned trusted JS tooling required')


@pytest.fixture(scope='module')
def installed(tmp_path_factory):
    directory = tmp_path_factory.mktemp('installed-js-wheel')
    wheels = directory / 'wheels'; wheels.mkdir()
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
                    '-w', str(wheels), str(ROOT)], check=True, capture_output=True, text=True, timeout=60)
    target = directory / 'target'
    wheel = next(wheels.glob('jev_integration_evaluator-*.whl'))
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--target', str(target), str(wheel)], check=True,
                   capture_output=True, text=True, timeout=60)
    return target


@pytest.mark.parametrize('format_name', ['esm', 'commonjs', 'typescript'])
def test_installed_cli_entrypoint_lifecycle_and_rollback(tmp_path, installed, format_name):
    root, source, spec, cases = host_fixture(tmp_path, format_name)
    original = source.read_bytes()
    spec_file, case_file = tmp_path / 'spec.json', tmp_path / 'cases.json'
    spec_file.write_text(json.dumps(spec), encoding='utf-8')
    case_file.write_text(json.dumps(cases), encoding='utf-8')
    bundle = tmp_path / 'bundle'
    env = dict(os.environ, PYTHONPATH=str(installed))

    def invoke(operation, *extra):
        done = subprocess.run([sys.executable, '-m', 'jev_integration_evaluator', operation,
                               '--repo', str(root), '--bundle', str(bundle),
                               '--tooling', str(ROOT), *extra],
                              cwd=tmp_path, env=env, capture_output=True, text=True,
                              timeout=40, check=True)
        return json.loads(done.stdout)

    plan = invoke('js-plan', '--spec', str(spec_file))
    baseline = invoke('js-verify', '--phase', 'baseline', '--cases', str(case_file),
                      '--approve-execution')
    assert baseline['status'] == 'passed'
    applied = invoke('js-apply', '--approve', plan['bundle_sha256'],
                     '--baseline-sha256', baseline['receipt_sha256'])
    assert applied['status'] == 'applied_unverified'
    modified = invoke('js-verify', '--phase', 'modified', '--cases', str(case_file),
                      '--approve-execution', '--baseline-sha256', baseline['receipt_sha256'])
    assert modified['status'] == 'passed'
    verified = invoke('js-status', '--trusted-modified-sha256', modified['receipt_sha256'])
    assert verified['status'] == 'verified'
    assert invoke('js-rollback', '--approve', verified['rollback_digest'])['status'] == 'rolled_back'
    assert source.read_bytes() == original
