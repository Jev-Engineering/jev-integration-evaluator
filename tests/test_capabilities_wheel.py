"""Installed-wheel discovery uses packaged schemas and never imports the target."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != 'posix', reason='Descriptor-relative discovery is currently qualified only on POSIX')
def test_installed_wheel_exposes_central_discovery_and_nomination(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path / 'dist'
    dist.mkdir()
    build = subprocess.run(
        [sys.executable, '-c', 'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))', str(dist)],
        cwd=root, capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stderr
    installed = tmp_path / 'installed'
    install = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(installed), str(next(dist.glob('*.whl')))],
        capture_output=True, text=True, timeout=60)
    assert install.returncode == 0, install.stderr
    target = tmp_path / 'target'
    target.mkdir()
    source = ('raise RuntimeError("TARGET MUST NOT EXECUTE")\n\n'
              'def n4(p):\n    return p.dispatch()\n\n'
              'def v8(p):\n    return n4(p)\n')
    (target / 'opaque.py').write_text(source, encoding='utf-8')
    bootstrap = '''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from jev_integration_evaluator import cli, capabilities
assert Path(cli.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
assert Path(capabilities.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
raise SystemExit(cli.main(sys.argv[2:]))
'''
    def run(*args):
        return subprocess.run([sys.executable, '-I', '-c', bootstrap, str(installed), *args],
                              cwd=tmp_path, capture_output=True, text=True, timeout=30)
    report_path = tmp_path / 'report.json'
    result = run('discover-capabilities', '--repo', str(target), '--out', str(report_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'written'
    report = json.loads(report_path.read_text())
    assert report['discovery_outcome'] == 'review_required'
    seam = next(row for row in report['seams'] if row['source']['qualified_symbol'] == 'v8')
    source_ref = seam['source']
    nomination = {'schema_version': '1.0', 'discovery_version': report['discovery_version'],
                  'report_sha256': report['report_sha256'], 'seam_id': seam['seam_id'],
                  'source': source_ref, 'pattern': 'C', 'proposer': 'synthetic-wheel-test',
                  'rationale': 'Opaque dispatch hypothesis requiring semantic review.',
                  'evidence': [{k: source_ref[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}]}
    proposal_path = tmp_path / 'nomination.json'
    proposal_path.write_text(json.dumps(nomination), encoding='utf-8')
    admitted_path = tmp_path / 'admitted.json'
    result = run('nominate-candidate', '--repo', str(target), '--nomination', str(proposal_path),
                 '--report-sha256', report['report_sha256'], '--out', str(admitted_path))
    assert result.returncode == 0, result.stderr
    admitted = json.loads(admitted_path.read_text())
    assert admitted['semantic_review'] == 'not_performed'
    assert not admitted['execution_qualified'] and not any(admitted['authorization'].values())
    for path, kind in ((report_path, 'repository-capabilities'), (proposal_path, 'candidate-nomination'),
                       (admitted_path, 'admitted-nomination')):
        result = run('validate', '--kind', kind, '--input', str(path))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['source_revalidated'] is False
    assert (target / 'opaque.py').read_text() == source
    assert set(p.name for p in target.iterdir()) == {'opaque.py'}
    assert os.stat(report_path).st_mode & 0o777 == os.stat(admitted_path).st_mode & 0o777 == 0o600
