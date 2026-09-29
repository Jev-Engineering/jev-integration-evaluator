"""Read-only native Windows console-source preflight; grants no delivery authority."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jev_integration_evaluator import capabilities as cap  # noqa: E402
from jev_integration_evaluator.io import InputError  # noqa: E402
from jev_integration_evaluator.windows_template_preflight import (  # noqa: E402
    inspect_windows_template_source,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'status': 'blocked', 'reason': 'invalid_command_arguments'}))
        raise SystemExit(2)


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output-parent', required=True)
    args = parser.parse_args(argv)
    try:
        if os.name != 'nt':
            raise InputError('native_windows_preflight_required')
        if cap._path_is_within(args.manifest, args.repo):
            raise InputError('windows_source_manifest_must_be_external')
        raw = cap._windows_secure_input(Path(args.manifest), 100_000)

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate')
                result[key] = value
            return result

        try:
            manifest = json.loads(raw, object_pairs_hook=unique)
        except (UnicodeError, ValueError):
            raise InputError('invalid_windows_source_manifest') from None
        if (type(manifest) is not dict or set(manifest) != {'schema_version', 'files'}
                or manifest['schema_version'] != '1.0'):
            raise InputError('invalid_windows_source_manifest')
        report = inspect_windows_template_source(args.repo, manifest['files'], args.output_parent)
        # Do not print target relative filenames or source. The API returns the
        # full private report when the caller has its own owner-private writer.
        public = {k: report[k] for k in ('schema_version', 'status', 'profile',
                  'source_manifest_sha256', 'file_count', 'target_modified',
                  'target_executed', 'apply_authorized', 'install_authorized',
                  'launch_authorized', 'output_private_creation', 'execution_boundary')}
        print(json.dumps(public, sort_keys=True))
        return 0
    except (InputError, cap.CapabilityError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        return 2
    except OSError:
        print(json.dumps({'status': 'blocked', 'reason': 'windows_preflight_io_unavailable'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
