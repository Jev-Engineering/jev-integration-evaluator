"""Thin, read-only entrypoint for the fixed repository-discovery conclude stage."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_integration_evaluator.repository_discovery import main

if __name__ == '__main__':
    if any(arg == '--stage' or arg.startswith('--stage=') for arg in sys.argv[1:]):
        print(json.dumps({'status': 'blocked', 'reason': 'invalid_command_arguments'}))
        raise SystemExit(2)
    raise SystemExit(main(['--stage', 'conclude', *sys.argv[1:]]))
