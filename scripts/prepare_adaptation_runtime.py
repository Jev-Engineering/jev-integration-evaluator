"""Exact offline generated Python adaptation adapter lifecycle.

The trusted review digest must come from an independent retained channel.
This command never imports a target module or executes a target entrypoint.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jev_integration_evaluator.io import InputError, read_json
from jev_integration_evaluator.integrations.adaptation_adapter_lifecycle import (
    plan_generated_adapter, apply_generated_adapter,
    generated_adapter_status, rollback_generated_adapter)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    planned = sub.add_parser('plan', help='write a private source and caller bound adapter plan')
    for flag in ('repo', 'request', 'spec', 'inventory', 'caller-review', 'out'):
        planned.add_argument('--' + flag, required=True)
    planned.add_argument('--trusted-adaptation-verification-sha256',
                         help='externally retained verified adaptation result digest, required for final stage')
    applied = sub.add_parser('apply', help='apply only the approved exact adapter bytes')
    applied.add_argument('--repo', required=True)
    applied.add_argument('--bundle', required=True)
    applied.add_argument('--approve', required=True)
    applied.add_argument('--trusted-caller-review-sha256', required=True)
    status = sub.add_parser('status', help='read local adapter state without promoting a receipt')
    status.add_argument('--repo', required=True)
    status.add_argument('--bundle', required=True)
    rollback = sub.add_parser('rollback', help='restore only matching owned adapter bytes')
    rollback.add_argument('--repo', required=True)
    rollback.add_argument('--bundle', required=True)
    rollback.add_argument('--approve', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'plan':
            result = plan_generated_adapter(args.repo, read_json(args.request),
                read_json(args.spec), read_json(args.inventory),
                read_json(args.caller_review), args.out,
                verify_adaptation=lambda kind, value: kind == 'verified_adaptation'
                and value == args.trusted_adaptation_verification_sha256)
        elif args.command == 'apply':
            result = apply_generated_adapter(args.repo, args.bundle, args.approve,
                verify_review=lambda kind, value: kind == 'adaptation_caller_review'
                and value == args.trusted_caller_review_sha256)
        elif args.command == 'status':
            result = generated_adapter_status(args.repo, args.bundle)
        else:
            result = rollback_generated_adapter(args.repo, args.bundle, args.approve)
    except (InputError, OSError, ValueError) as error:
        print(json.dumps({'status': 'rejected', 'error': type(error).__name__,
                          'message': str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
