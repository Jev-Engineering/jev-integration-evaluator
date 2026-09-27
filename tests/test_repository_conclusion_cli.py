"""Real staged CLI invocations over disposable, hand-authored source only."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.cli import main
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
from jev_integration_evaluator.repository_conclusion import coverage_review_schedule, REVIEW_CONTRACT


def setup(tmp_path):
    repo = tmp_path / 'opaque-private-host'
    repo.mkdir()
    (repo / 'opaque.py').write_bytes(b"def a9(q):\n    return q.get('value')\n\ndef x3(q):\n    return a9(q)\n")
    report = discover_repository_capabilities(repo, copy.deepcopy(DEFAULT))
    report_path = tmp_path / 'capabilities.json'
    report_path.write_bytes(cap._json(report))
    schedule = coverage_review_schedule(report, copy.deepcopy(DEFAULT))
    review = {'schema_version': '1.0', 'contract': REVIEW_CONTRACT,
              **{k: schedule[k] for k in ('report_sha256', 'conclusion_engine_sha256',
                                          'settings_sha256', 'objective_sha256')},
              'reviewer': 'synthetic-fixture-not-human-authentication', 'files': [], 'seams': []}
    for kind in ('files', 'seams'):
        review[kind] = [{**r, 'patterns': {p: {'disposition': 'not_useful',
                       'reason': 'Synthetic test opinion; no observed deployment benefit is asserted.'}
                       for p in 'ABCDEFGHIJKLM'}} for r in schedule[kind]]
    review_path = tmp_path / 'coverage-review.json'
    review_path.write_bytes(cap._json(review))
    return repo, report_path, review_path, review


def command(repo, report_path, out, review_path=None, digest=None):
    args = ['repository-discovery', str(repo), '--stage', 'conclude',
            '--capabilities', str(report_path), '--out', str(out)]
    if review_path: args += ['--coverage-review', str(review_path)]
    if digest: args += ['--review-sha256', digest]
    return args


def test_real_module_cli_complete_scoped_negative_and_private_output(tmp_path):
    repo, report_path, review_path, review = setup(tmp_path)
    before = (repo / 'opaque.py').read_bytes()
    out = tmp_path / 'result.json'
    run = subprocess.run([sys.executable, '-m', 'jev_integration_evaluator',
                          *command(repo, report_path, out, review_path, cap._digest(review))],
                         text=True, capture_output=True, check=False)
    assert run.returncode == 0, run.stderr
    stdout = json.loads(run.stdout)
    assert stdout['outcome'] == 'no_useful_placement'
    assert 'opaque-private-host' not in run.stdout + run.stderr
    result = json.loads(out.read_text())
    assert result['outcome'] == 'no_useful_placement'
    assert not any(result['authorization'].values())
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert (repo / 'opaque.py').read_bytes() == before
    assert set(p.name for p in repo.iterdir()) == {'opaque.py'}


def test_main_missing_reviews_is_read_only_and_structured(tmp_path, capsys):
    repo, report_path, _, _ = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out)) == 0
    data = json.loads(out.read_text())
    assert data['outcome'] == 'review_required'
    assert data['coverage']['unresolved_pattern_reviews'] == 39
    assert json.loads(capsys.readouterr().out)['next_actions']


def test_complete_review_without_anchor_stays_insufficient(tmp_path):
    repo, report_path, review_path, _ = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, review_path)) == 0
    assert json.loads(out.read_text())['outcome'] == 'insufficient_evidence'


def test_anchor_without_review_is_rejected(tmp_path, capsys):
    repo, report_path, _, _ = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, digest='f' * 64)) == 2
    assert not out.exists()
    assert 'coverage_review_required_for_anchor' in capsys.readouterr().out


@pytest.mark.parametrize('extra', [
    ['--objective', 'private-objective'], ['--coverage-review', 'private-review-path'],
    ['--review-sha256', '0' * 64],
])
def test_conclude_options_are_not_silently_ignored_on_old_stages(tmp_path, capsys, extra):
    repo, _, _, _ = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(['repository-discovery', str(repo), '--out', str(out), *extra]) == 2
    assert not out.exists()
    assert 'private-' not in capsys.readouterr().out


def test_existing_output_is_not_replaced(tmp_path):
    repo, report_path, review_path, review = setup(tmp_path)
    out = tmp_path / 'result.json'
    out.write_bytes(b'belongs-to-another-operation')
    assert main(command(repo, report_path, out, review_path, cap._digest(review))) == 2
    assert out.read_bytes() == b'belongs-to-another-operation'


def test_output_inside_target_is_not_written(tmp_path):
    repo, report_path, review_path, review = setup(tmp_path)
    out = repo / 'must-not-exist.json'
    assert main(command(repo, report_path, out, review_path, cap._digest(review))) == 2
    assert not out.exists()


def test_coverage_review_inside_target_is_not_treated_as_external_review(tmp_path):
    repo, report_path, _, review = setup(tmp_path)
    rv = repo / 'review.json'
    rv.write_bytes(cap._json(review))
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, rv, cap._digest(review))) == 2
    assert not out.exists()


@pytest.mark.parametrize('kind', ['review', 'output_parent', 'report'])
def test_symlink_paths_fail_without_touching_destination(tmp_path, kind):
    repo, report_path, review_path, review = setup(tmp_path)
    out = tmp_path / 'result.json'
    link = tmp_path / 'untrusted-link'
    if kind == 'review':
        link.symlink_to(review_path); review_path = link
    elif kind == 'report':
        link.symlink_to(report_path); report_path = link
    else:
        actual = tmp_path / 'actual-directory'; actual.mkdir()
        link.symlink_to(actual, target_is_directory=True); out = link / 'result.json'
    assert main(command(repo, report_path, out, review_path, cap._digest(review))) == 2
    assert not out.exists()


@pytest.mark.parametrize('raw', [b'{"reviewer":"PRIVATE-CONTENT","reviewer":"another"}',
                                b'{"reviewer":"PRIVATE-CONTENT","x":NaN}',
                                b'{"reviewer":"PRIVATE-CONTENT"'])
def test_untrusted_json_errors_are_redacted(tmp_path, capsys, raw):
    repo, report_path, review_path, _ = setup(tmp_path)
    review_path.write_bytes(raw)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, review_path)) == 2
    assert not out.exists()
    assert 'PRIVATE-CONTENT' not in capsys.readouterr().out


def test_private_unrecognized_arguments_are_redacted(tmp_path, capsys):
    repo, _, _, _ = setup(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(['repository-discovery', str(repo), '--out', str(tmp_path / 'out'),
              '--PRIVATE-CREDENTIAL=do-not-echo'])
    assert caught.value.code == 2
    assert 'PRIVATE-CREDENTIAL' not in capsys.readouterr().out


def test_shape_validation_is_not_source_revalidation(tmp_path, capsys):
    repo, report_path, review_path, review = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, review_path, cap._digest(review))) == 0
    capsys.readouterr()
    (repo / 'opaque.py').write_bytes(b'# changed after conclusion\n')
    assert main(['validate', '--kind', 'repository-conclusion-v1', '--input', str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['source_revalidated'] is False


def test_validate_rejects_conclusion_digest_tampering(tmp_path, capsys):
    repo, report_path, review_path, review = setup(tmp_path)
    out = tmp_path / 'result.json'
    assert main(command(repo, report_path, out, review_path, cap._digest(review))) == 0
    capsys.readouterr()
    result = json.loads(out.read_text()); result['reviewer_claim'] = 'different-reviewer'
    out.write_bytes(cap._json(result))
    assert main(['validate', '--kind', 'repository-conclusion-v1', '--input', str(out)]) == 2
    assert 'repository_conclusion_digest_mismatch' in capsys.readouterr().err


def test_review_json_is_not_imported_or_evaluated(tmp_path):
    repo, report_path, review_path, review = setup(tmp_path)
    marker = tmp_path / 'must-not-exist'
    review['reviewer'] = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    review_path.write_bytes(cap._json(review))
    assert main(command(repo, report_path, tmp_path / 'result.json', review_path, cap._digest(review))) == 0
    assert not marker.exists()


def test_thin_script_cannot_switch_stages(tmp_path):
    repo, report_path, review_path, review = setup(tmp_path)
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'conclude_repository.py'
    out = tmp_path / 'thin.json'
    args = [sys.executable, str(script), str(repo), '--capabilities', str(report_path),
            '--coverage-review', str(review_path), '--review-sha256', cap._digest(review), '--out', str(out)]
    run = subprocess.run(args, text=True, capture_output=True, timeout=30)
    assert run.returncode == 0
    assert json.loads(out.read_text())['outcome'] == 'no_useful_placement'
    before = out.read_bytes()
    blocked = subprocess.run([*args, '--stage=discover'], text=True, capture_output=True, timeout=30)
    assert blocked.returncode == 2 and out.read_bytes() == before


def test_fresh_synthetic_demo_outputs_are_source_linked_and_not_reusable(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'run_repository_conclusion_demo.py'
    out = tmp_path / 'fresh'
    run = subprocess.run([sys.executable, str(script), '--out', str(out)],
                         text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    summary = json.loads(run.stdout)
    assert summary['outcomes'] == ['review_required', 'insufficient_evidence', 'no_useful_placement']
    assert summary['review_opinion_slots'] == 39
    assert not summary['source_imported_or_executed'] and not summary['independent_corpus_qualified']
    before = (out / 'summary.json').read_bytes()
    again = subprocess.run([sys.executable, str(script), '--out', str(out)],
                           text=True, capture_output=True, timeout=30)
    assert again.returncode == 2 and (out / 'summary.json').read_bytes() == before
