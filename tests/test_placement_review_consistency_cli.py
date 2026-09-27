"""Actual thin-script calls for conflicting review outcomes; synthetic hosts only."""
from __future__ import annotations
import json
import os

import pytest

from test_repository_placement_selection import factory, context, request, cli_files, call_cli
from test_placement_review_consistency import _inconsistent

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Secure source discovery currently qualifies POSIX')


@pytest.mark.parametrize('kind', ['negative_file_positive_candidate', 'negative_seam_positive_candidate'])
def test_cli_mixed_review_cannot_select_a_candidate(factory, tmp_path, kind):
    case = factory(extra={'other.py': 'VALUE = 11\n'})
    paths = cli_files(case, tmp_path)
    review = _inconsistent(case, kind)
    scope = tmp_path/'scope-review.json'
    scope.write_text(json.dumps(review), encoding='utf-8')
    ctx = context(case, review)
    ids = [c['candidate_id'] for c in case['prepared']['inventory']['candidates']]
    req = tmp_path/'selection-review.json'
    req.write_text(json.dumps(request(ctx, ids=ids)), encoding='utf-8')
    output = tmp_path/'blocked-selection.json'
    before = {p.name: (p.read_bytes(), p.stat().st_mode) for p in case['repo'].rglob('*') if p.is_file()}
    proc = call_cli(case, paths, output, '--scope-review', str(scope),
                    '--selection-review', str(req), operation='select')
    assert proc.returncode == 2, proc.stderr
    assert proc.stderr == ''
    summary = json.loads(proc.stdout)
    assert summary['outcome'] == 'blocked'
    assert summary['next_action'] == 'resolve_selection_failures'
    assert 'opaque.py' not in proc.stdout and str(case['repo']) not in proc.stdout
    result = json.loads(output.read_text())
    assert result['selected_count'] == 0 and result['requested_count'] == len(ids)
    assert result['placements'] == [] and result['selected_candidate_ids'] == []
    assert {row['reason'] for row in result['failures']} == {'insufficient_evidence'}
    assert not any(result['authorization'].values()) and not result['benefit_supported']
    assert output.stat().st_mode & 0o777 == 0o600
    after = {p.name: (p.read_bytes(), p.stat().st_mode) for p in case['repo'].rglob('*') if p.is_file()}
    assert before == after


def test_cli_mixed_scope_context_exposes_conflict_action(factory, tmp_path):
    case = factory(approved=False, extra={'other.py': 'VALUE = 11\n'})
    paths = cli_files(case, tmp_path)
    review = _inconsistent(case, 'negative_file_unnominated_positive_seam')
    scope = tmp_path/'scope-review.json'; scope.write_text(json.dumps(review), encoding='utf-8')
    output = tmp_path/'unresolved-context.json'
    proc = call_cli(case, paths, output, '--scope-review', str(scope))
    assert proc.returncode == 0, proc.stderr  # writing an outcome is not selecting
    summary = json.loads(proc.stdout)
    assert summary['outcome'] == 'insufficient_evidence'
    assert summary['next_action'] == 'reconcile_conflicting_semantic_reviews'
    assert json.loads(output.read_text())['scope_review']['useful'] == 2
    assert 'opaque.py' not in proc.stdout and proc.stderr == ''
