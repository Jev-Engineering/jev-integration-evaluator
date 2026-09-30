"""Finite test-owned installer child; a parent Job owns every spawned process."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys
import time


def main() -> int:
    # The parent creates our launcher suspended and assigns its Job before resuming it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from jev_integration_evaluator import windows_template_install as install

    plan_path, marker_path, phase = sys.argv[1:]
    if phase not in ('durable_intent', 'host_installed', 'before_receipt'):
        return 2
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    root = install._generation(plan)
    real_write, real_run = install.write_private_json_exclusive, install._run

    def checkpoint() -> None:
        record = {'phase': phase, 'pid': os.getpid(), 'plan_sha256': plan['plan_sha256']}
        pending = Path(marker_path).with_suffix('.pending.json')
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, marker_path)
        # Parent must terminate us; expiry is a failed test, never success.
        time.sleep(180)
        raise RuntimeError('fixture_checkpoint_expired')

    def write(owned, name, value):
        if phase == 'before_receipt' and name == 'install-receipt.json':
            checkpoint()
        result = real_write(owned, name, value)
        if phase == 'durable_intent' and name == 'install-intent.json':
            checkpoint()
        return result

    def run(command, **kwargs):
        result = real_run(command, **kwargs)
        if phase == 'host_installed' and str(root / 'host.lock') in command:
            checkpoint()
        return result

    install.write_private_json_exclusive, install._run = write, run
    try:
        install.install_windows_template_package(
            plan, approved_plan_sha256=plan['plan_sha256'])
    except Exception as exc:
        # Bounded diagnosis without command output, private paths or source bytes.
        failure = {'phase': phase, 'error_type': type(exc).__name__}
        if isinstance(exc, install.InputError) and re.fullmatch(r'[a-z][a-z0-9_]{0,100}', str(exc)):
            failure['error_code'] = str(exc)
        Path(marker_path).with_suffix('.failure.json').write_text(
            json.dumps(failure, sort_keys=True), encoding='utf-8')
        raise
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
