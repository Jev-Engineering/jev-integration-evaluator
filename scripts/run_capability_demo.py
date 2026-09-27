"""Build a synthetic, read-only discovery-to-semantic-review demonstration."""
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
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.nomination_inventory import (
    discover_repository_capabilities, prepare_nominated_inventory,
    review_nominated_inventory,
)


def records(host: Path) -> dict:
    cfg = load_config()
    report = discover_repository_capabilities(host, cfg)
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol'] == 'z93')
    anchor = copy.deepcopy(seam['source'])
    nomination = {
        'schema_version': '1.0', 'discovery_version': cap.VERSION,
        'report_sha256': report['report_sha256'], 'seam_id': seam['seam_id'],
        'source': anchor, 'pattern': 'C', 'proposer': 'assistant-authored-synthetic-demo',
        'rationale': 'Finite queue routing is a placement hypothesis requiring semantic review.',
        'evidence': [{k: anchor[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}],
    }
    prepared = prepare_nominated_inventory(host, report, [nomination], cfg)
    candidate = next(c for c in prepared['inventory']['candidates']
                     if c['source']['symbol'] == 'z93' and c['pattern'] == 'C')
    review = {
        'schema_version': '1.0', 'prepared_sha256': prepared['prepared_sha256'],
        'reviews': {candidate['candidate_id']: {
            'source_sha256': candidate['source']['source_sha256'],
            'reviewer': 'assistant-authored-synthetic-review',
            'reason': ('z93 delegates to a17, whose existing keyword rule selects queue-7 '
                       'for refund and queue-2 otherwise. This fixture supplies no observed '
                       'failure or requirement that justifies replacing that rule with JEV.'),
            'approved': False, 'deterministic_alternative': 'preferred',
        }},
    }
    reviewed = review_nominated_inventory(host, report, prepared, review, cfg)
    assert not reviewed['runtime_activation_authorized']
    assert not reviewed['implementation_verified']
    return {'capabilities': report, 'nomination': nomination, 'nominations': [nomination],
            'admission': prepared['admissions'][0], 'policy': report['policy'],
            'prepared': prepared, 'review': review, 'reviewed': reviewed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New private directory outside this checkout')
    args = parser.parse_args(argv)
    try:
        requested = Path(args.out).absolute()
        if requested == ROOT or ROOT in requested.parents:
            raise cap.CapabilityError('output_must_be_outside_checkout')
        parent, fd = cap._open_directory(requested.parent)
        try:
            os.mkdir(requested.name, mode=0o700, dir_fd=fd)
        finally:
            os.close(fd)
        out = parent / requested.name
        host = ROOT / 'examples' / 'repository-capabilities' / 'host'
        values = records(host)
        for name, value in values.items():
            cap._write_out(out / (name + '.json'), ROOT, value)
        print(json.dumps({'status': 'passed', 'records': len(values), 'synthetic': True,
                          'host_executed': False, 'semantic_approved': False,
                          'implementation_verified': False, 'network_requests': 0}))
        return 0
    except (cap.CapabilityError, OSError, StopIteration) as exc:
        code = exc.code if isinstance(exc, cap.CapabilityError) else 'demo_input_or_output_unavailable'
        print(json.dumps({'status': 'blocked', 'reason': code}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
