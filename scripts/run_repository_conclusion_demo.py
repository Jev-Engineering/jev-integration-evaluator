"""Generate source-linked conclusion examples from a fresh synthetic host only.

There is deliberately no repository/provider argument. The built-in negative
opinions are synthetic qualification data, never answers for a user's source.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator.config import DEFAULT
from jev_integration_evaluator.nomination_inventory import discover_repository_capabilities
from jev_integration_evaluator.repository_conclusion import (
    REVIEW_CONTRACT, conclude_repository, coverage_review_schedule)

SOURCE = "def a9(q):\n    return q.get('route')\n\ndef x3(q):\n    return a9(q)\n"


def run(output: Path) -> dict:
    output = Path(os.path.abspath(output))
    if output == ROOT or ROOT in output.parents:
        raise cap.CapabilityError('demo_output_must_be_external')
    _, fd = cap._open_directory(output.parent)
    try:
        os.mkdir(output.name, mode=0o700, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)
    host = output / 'synthetic-host'
    host.mkdir(mode=0o700)
    path = host / 'opaque.py'
    with path.open('x', encoding='utf-8') as stream:
        stream.write(SOURCE)
    path.chmod(0o600)
    before = path.read_bytes()
    cfg = copy.deepcopy(DEFAULT)
    report = discover_repository_capabilities(host, cfg)
    schedule = coverage_review_schedule(report, cfg)
    review = {'schema_version': '1.0', 'contract': REVIEW_CONTRACT,
              **{k: schedule[k] for k in ('report_sha256', 'conclusion_engine_sha256',
                                          'settings_sha256', 'objective_sha256')},
              'reviewer': 'assistant-authored-synthetic-fixture-not-principal-authentication'}
    for kind in ('files', 'seams'):
        review[kind] = [{**row, 'patterns': {pattern: {
            'disposition': 'not_useful',
            'reason': 'Synthetic fixture opinion: this bounded dictionary lookup and tail forwarding '
                      'supply no source-supported need for pattern ' + pattern + '.'}
            for pattern in 'ABCDEFGHIJKLM'}} for row in schedule[kind]]
    missing = conclude_repository(host, report, cfg)
    unanchored = conclude_repository(host, report, cfg, review=review)
    # Synthetic harness authority only. A real caller must authenticate the
    # reviewer and retain its reviewed digest outside untrusted target records.
    anchored = conclude_repository(host, report, cfg, review=review,
                                    expected_review_sha256=cap._digest(review))
    assert [row['outcome'] for row in (missing, unanchored, anchored)] == [
        'review_required', 'insufficient_evidence', 'no_useful_placement']
    assert before == path.read_bytes() and len(list(host.iterdir())) == 1
    assert not any(anchored['authorization'].values()) and anchored['benefit'] is None
    artifacts = {'capabilities': report, 'review-schedule': schedule, 'coverage-review': review,
                 'without-review': missing, 'unanchored-review': unanchored,
                 'anchored-conclusion': anchored}
    for name, record in artifacts.items():
        cap._write_out(output / (name + '.json'), host, record)
    summary = {'status': 'passed', 'classification': 'assistant_authored_synthetic',
               'source_imported_or_executed': False, 'provider_used': False,
               'source_unchanged': True, 'independent_corpus_qualified': False,
               'runtime_activation_authorized': False, 'benefit': None,
               'outcomes': [row['outcome'] for row in (missing, unanchored, anchored)],
               'review_opinion_slots': 13 * (len(report['files']) + len(report['seams'])),
               'conclusion_sha256': anchored['conclusion_sha256']}
    cap._write_out(output / 'summary.json', host, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out)))
        return 0
    except (cap.CapabilityError, OSError, ValueError):
        print(json.dumps({'status': 'blocked', 'reason': 'invalid_or_unavailable_demo_output'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
