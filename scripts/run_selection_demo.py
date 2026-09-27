#!/usr/bin/env python3
"""Offline, generated-fixture selection demo; no independent/observed-benefit claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.io import digest, write_json
from jev_integration_evaluator.selection import prepare_experimental_plan, request_sha256, selection_engine_sha256
from scripts.implementation_fixtures import fixture


def run(out: Path, *, verify_synthetic_lifecycle: bool = False) -> dict:
    checkout = Path(__file__).resolve().parents[1]
    out = out.resolve()
    if out == checkout or checkout in out.parents:
        raise ValueError('demo_output_must_be_outside_checkout')
    # Never reuse an earlier demonstration or overwrite an existing directory.
    out.mkdir(mode=0o700)
    host, bundle = out/'synthetic-host', out/'private-bundle'
    inventory, spec = fixture(host, 'C', tag='experimental_selection_demo')
    request = {
        'schema_version': '1.0', 'selection_engine_sha256': selection_engine_sha256(), 'mode': 'experimental',
        'inventory_sha256': digest(inventory), 'candidate_id': spec['candidate_id'],
        'decision_review': {'reviewer': 'offline-synthetic-demo',
            'reason': 'Prepare a generated local fixture with unknown benefit; no live authority.',
            'evidence_refs': ['synthetic-fixture:experimental-selection-C']},
        'preparation_scope_ref': 'demo-owned-disposable-fixture',
        'implementation_spec_sha256': digest(spec), 'constraints': None,
        'live_limits': {'max_total_cost': None, 'max_total_calls': None, 'max_concurrent_calls': None},
    }
    before = {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}
    write_json(out/'selection-envelope.json', {'schema_version': '1.0', 'inventory': inventory,
                                              'request': request, 'specification': spec})
    # This approval is for this script's own synthetic fixture only. Computing
    # a digest of an arbitrary proposal is not user approval.
    prepared = prepare_experimental_plan(host, inventory, request, spec, bundle,
                                         approved_request_sha256=request_sha256(request))
    assert prepared['implementation']['status'] == 'planned'
    assert before == {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}
    write_json(out/'selection.json', prepared['selection'])
    summary = {
        'classification': 'synthetic_generated_fixture_not_independent_corpus',
        'selection_status': prepared['selection']['status'],
        'implementation_status': 'planned',
        'selected_estimates_all_unknown': all(v is None for v in
            prepared['selection']['selected_estimates'][spec['candidate_id']].values()),
        'target_unchanged_after_preparation': True, 'lifecycle_executed': False,
        'live_provider_executed': False, 'real_bootstrap_qualified': False,
        'native_isolation_qualified': False, 'benefit_demonstrated': False,
        'production_activation_authorized': False,
    }
    if verify_synthetic_lifecycle:
        from jev_integration_evaluator.integrations.lifecycle import (
            apply_implementation, implementation_status, rollback_implementation)
        from jev_integration_evaluator.integrations.verification import verify_implementation
        baseline = verify_implementation(host, bundle, 'baseline', approve_execution=True)
        assert baseline['status'] == 'baseline_passed'
        applied = apply_implementation(host, bundle, prepared['implementation']['bundle_digest'],
                                       baseline_sha256=baseline['receipt_sha256'])
        modified = verify_implementation(host, bundle, 'modified', approve_execution=True,
                                          baseline_sha256=baseline['receipt_sha256'])
        assert modified['status'] == 'verified'
        assert implementation_status(host, bundle, trusted_receipt_sha256=modified['receipt_sha256'])['status'] == 'verified'
        rolled_back = rollback_implementation(host, bundle, applied['rollback_digest'])
        assert rolled_back['status'] == 'rolled_back'
        assert before == {p.relative_to(host): p.read_bytes() for p in host.rglob('*') if p.is_file()}
        summary.update(lifecycle_executed=True, baseline_status=baseline['status'],
                       modified_status=modified['status'], rollback_status=rolled_back['status'],
                       baseline_scheduled_cases=baseline['scheduled_cases'],
                       baseline_passed_cases=baseline['passed_cases'],
                       modified_scheduled_cases=modified['scheduled_cases'],
                       modified_passed_cases=modified['passed_cases'], target_restored=True)
    write_json(out/'summary.json', summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verify-synthetic-lifecycle', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = run(args.out, verify_synthetic_lifecycle=args.verify_synthetic_lifecycle)
    except (ValueError, OSError, AssertionError):
        print(json.dumps({'error': 'synthetic_demo_failed_or_output_unavailable'}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
