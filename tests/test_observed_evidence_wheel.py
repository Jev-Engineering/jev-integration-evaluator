"""Offline installed-wheel check for the new CLI and mirrored contracts."""
from pathlib import Path
import subprocess
import sys


def test_installed_wheel_exposes_observed_commands_and_contracts(tmp_path):
    source = Path(__file__).resolve().parents[1]
    dist = tmp_path / 'dist'
    dist.mkdir()
    build = subprocess.run([sys.executable, '-c',
        'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',
        str(dist)], cwd=source, capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stderr
    installed = tmp_path / 'installed'
    install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index',
        '--no-deps', '--target', str(installed), str(next(dist.glob('*.whl')))],
        capture_output=True, text=True, timeout=60)
    assert install.returncode == 0, install.stderr
    code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import jev_integration_evaluator as package
assert Path(package.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.observed_evidence import OfflineFixtureHost
assert OfflineFixtureHost.__module__.startswith('jev_integration_evaluator.')
for name in ('observed-link', 'observed-check', 'observed-collect-offline', 'observed-evaluate'):
    try:
        main([name, '--help'])
    except SystemExit as exc:
        assert exc.code == 0
for name in ('observed-link', 'observed-placement-set', 'observed-collection-request', 'observed-collection', 'observed-evaluation'):
    try:
        validate_contract({}, name)
    except Exception as exc:
        assert 'not found' not in str(exc).lower()
    else:
        raise AssertionError('Strict observed contract accepted an empty record')
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(installed)],
        cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
