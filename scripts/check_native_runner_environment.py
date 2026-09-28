"""Fail closed when the dedicated disposable runner differs from reviewed bytes."""
from __future__ import annotations
import json
from pathlib import Path
from jev_integration_evaluator.runners.isolated_python import environment_identity

ROOT = Path(__file__).resolve().parents[1]
expected = json.loads((ROOT / 'validation/native-runner-environment-lock.json').read_text())
actual = environment_identity()
print(json.dumps(actual, sort_keys=True))
if actual != expected:
    changed = sorted(set(actual) ^ set(expected) | {
        key for key in set(actual) & set(expected) if actual[key] != expected[key]
    })
    raise SystemExit('unreviewed native runner environment: ' + ','.join(changed))
