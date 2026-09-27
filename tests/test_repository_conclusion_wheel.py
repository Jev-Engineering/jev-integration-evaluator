"""Install an offline wheel and exercise its real CLI from outside the checkout."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys


def test_installed_conclusion_preserves_scope_and_rechecks_source(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path / 'dist'; dist.mkdir()
    build = subprocess.run([sys.executable, '-c',
        'import setuptools.build_meta,sys;print(setuptools.build_meta.build_wheel(sys.argv[1]))',
        str(dist)], cwd=root, text=True, capture_output=True, timeout=90)
    assert build.returncode == 0, 'offline_wheel_build_failed'
    wheels = list(dist.glob('*.whl')); assert len(wheels) == 1
    installed = tmp_path / 'installed'
    install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                              '--target', str(installed), str(wheels[0])],
                             text=True, capture_output=True, timeout=90)
    assert install.returncode == 0, 'offline_wheel_install_failed'
    code = r'''
import contextlib, io, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
import jev_integration_evaluator.repository_conclusion as conclusion
assert Path(conclusion.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
work = Path(sys.argv[2]); host = work / 'synthetic'; host.mkdir()
source = host / 'opaque.py'
source.write_text('def f9(q):\n    return q.get("route")\n\ndef g7(q):\n    return f9(q)\n')
before = source.read_bytes()
report = discover_repository_capabilities(host, DEFAULT)
schedule = conclusion.coverage_review_schedule(report, DEFAULT)
review = {'schema_version': '1.0', 'contract': conclusion.REVIEW_CONTRACT,
          **{k: schedule[k] for k in ('report_sha256', 'conclusion_engine_sha256',
                                      'settings_sha256', 'objective_sha256')},
          'reviewer': 'synthetic-installed-test-not-authentication'}
for kind in ('files', 'seams'):
    review[kind] = [{**row, 'patterns': {p: {'disposition': 'not_useful',
        'reason': 'A synthetic schema and source-identity test opinion only.'}
        for p in 'ABCDEFGHIJKLM'}} for row in schedule[kind]]
report_path = work / 'report.json'; report_path.write_bytes(cap._json(report))
review_path = work / 'review.json'; review_path.write_bytes(cap._json(review))
output = work / 'result.json'
args = ['repository-discovery', str(host), '--stage', 'conclude',
        '--capabilities', str(report_path), '--coverage-review', str(review_path),
        '--review-sha256', cap._digest(review), '--out', str(output)]
stdout = io.StringIO()
with contextlib.redirect_stdout(stdout):
    assert main(args) == 0
result = json.loads(output.read_text())
assert result['outcome'] == 'no_useful_placement'
assert source.read_bytes() == before and len(list(host.iterdir())) == 1
assert output.stat().st_mode & 0o777 == 0o600
assert not any(result['authorization'].values())
assert result['benefit'] is None and not result['implementation_verified']
assert not result['scope']['global_absence_proven']
assert not result['review_principal_authenticated']
# Retrying against drift cannot replay an old successful conclusion.
source.write_text(source.read_text() + '\nchanged = True\n')
args[-1] = str(work / 'stale-result.json')
with contextlib.redirect_stdout(stdout):
    assert main(args) == 2
assert not (work / 'stale-result.json').exists()
assert str(host) not in stdout.getvalue()
print(json.dumps({'classification': 'synthetic', 'installed_import': True,
                  'read_only_conclusion': True, 'stale_source_rejected': True,
                  'provider_execution': False, 'activation': False, 'benefit': None}))
'''
    run = subprocess.run([sys.executable, '-I', '-c', code, str(installed), str(tmp_path)],
                         cwd=tmp_path, text=True, capture_output=True, timeout=90)
    assert run.returncode == 0, 'installed_conclusion_or_drift_rejection_failed'
    result = json.loads(run.stdout)
    assert result['installed_import'] and result['read_only_conclusion'] and result['stale_source_rejected']
    assert result['provider_execution'] is result['activation'] is False
    assert result['benefit'] is None
