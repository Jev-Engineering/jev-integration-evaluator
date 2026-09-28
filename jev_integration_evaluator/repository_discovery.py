"""Read-only discovery, inventory preparation and source-matched semantic review.

This command does not execute targets, implement the #4 mutation lifecycle,
activate a provider or publish Git. Supplied configuration and reviews are data.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import json
import os
from pathlib import Path

from . import capabilities as cap
from .config import DEFAULT
from .io import InputError
from .nomination_inventory import (MAX_RECORD_BYTES, _settings, discover_repository_capabilities,
                                   prepare_nominated_inventory, review_nominated_inventory)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argument-parser messages can contain private paths or review text.
        print(json.dumps({'status': 'blocked', 'reason': 'invalid_command_arguments'}))
        raise SystemExit(2)


def add_arguments(parser):
    parser.add_argument('repo', help='Repository to read without importing target code')
    parser.add_argument('--stage', choices=('discover', 'prepare', 'review', 'conclude'), default='discover')
    parser.add_argument('--out', required=True, help='New private JSON file outside the target')
    parser.add_argument('--config', help='External complete evaluator configuration as JSON data')
    parser.add_argument('--policy', help='External published discovery-policy JSON')
    parser.add_argument('--capabilities', help='Prior source-bound capability report JSON')
    parser.add_argument('--nominations', help='JSON array of published source-bound nominations')
    parser.add_argument('--prepared', help='Unreviewed inventory preparation JSON')
    parser.add_argument('--review', help='Source-bound semantic-review JSON; not execution authority')
    parser.add_argument('--coverage-review', help='External source-bound file/seam A-M opinions for conclude')
    parser.add_argument('--review-sha256', help='Coverage-review digest retained through a separate trusted channel')
    parser.add_argument('--objective', help='Bounded review objective for conclude; changing it invalidates review')


def _external_data(path, repo, *, max_bytes=cap.MAX_INPUT_BYTES):
    # Check resolved location but read the original path with the canonical
    # no-follow loader, so links cannot bypass the check.
    try:
        if os.name == 'nt':
            root, _ = cap._windows_absolute_path(repo)
            external, _ = cap._windows_absolute_path(path)
        else:
            root, external = Path(repo).resolve(strict=True), Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        raise cap.CapabilityError('input_unavailable_or_invalid') from None
    if cap._path_is_within(external, root):
        raise cap.CapabilityError('configuration_must_be_external')
    return cap._load(Path(path), max_bytes=max_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        present = {k for k in ('capabilities', 'nominations', 'prepared', 'review') if getattr(args, k)}
        required = {'discover': set(), 'prepare': {'capabilities', 'nominations'},
                    'review': {'capabilities', 'prepared', 'review'},
                    'conclude': {'capabilities'}}[args.stage]
        if present != required:
            raise cap.CapabilityError('stage_input_mismatch')
        if args.stage != 'conclude' and any(value is not None for value in (
                args.coverage_review, args.review_sha256, args.objective)):
            raise cap.CapabilityError('stage_input_mismatch')
        cfg = _external_data(args.config, args.repo) if args.config else copy.deepcopy(DEFAULT)
        policy = None
        if args.policy:
            supplied = _external_data(args.policy, args.repo)
            if type(supplied) is not dict:
                raise cap.CapabilityError('invalid_discovery_policy')
            defaults = json.loads(cap._json(asdict(_settings(cfg, None)[1])))
            policy = cap.DiscoveryPolicy.from_json({**defaults, **supplied})
        if args.stage == 'discover':
            result = discover_repository_capabilities(args.repo, cfg, policy=policy)
        else:
            report = cap._load(Path(args.capabilities), max_bytes=MAX_RECORD_BYTES)
            if args.stage == 'conclude':
                from .repository_conclusion import conclude_repository
                review = (_external_data(args.coverage_review, args.repo, max_bytes=MAX_RECORD_BYTES)
                          if args.coverage_review else None)
                result = conclude_repository(args.repo, report, cfg, policy=policy,
                                             objective=args.objective, review=review,
                                             expected_review_sha256=args.review_sha256)
            elif args.stage == 'prepare':
                nominations = cap._load(Path(args.nominations), max_bytes=MAX_RECORD_BYTES)
                result = prepare_nominated_inventory(args.repo, report, nominations, cfg, policy=policy)
            else:
                prepared = cap._load(Path(args.prepared), max_bytes=MAX_RECORD_BYTES)
                review = cap._load(Path(args.review), max_bytes=MAX_RECORD_BYTES)
                result = review_nominated_inventory(args.repo, report, prepared, review, cfg, policy=policy)
        if len(cap._json(result)) + 1 > MAX_RECORD_BYTES:
            raise cap.CapabilityError('inventory_bridge_byte_bound')
        cap._write_out(Path(args.out), Path(args.repo), result)
        summary = {'status': 'written', 'artifact_sha256': cap._digest(result)}
        if args.stage == 'conclude':
            summary.update(outcome=result['outcome'], next_actions=result['next_actions'])
        print(json.dumps(summary))
        return 0
    except (cap.CapabilityError, InputError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        reason = exc.code if isinstance(exc, cap.CapabilityError) else 'invalid_repository_discovery_input'
        print(json.dumps({'status': 'blocked', 'reason': reason}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({'status': 'blocked', 'reason': 'discovery_interrupted'}))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
