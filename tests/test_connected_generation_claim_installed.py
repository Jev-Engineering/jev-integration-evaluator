"""Two freshly bound M hosts share one installed synthetic connected ledger."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from tests.connected_generation_journey import GenerationJourney, run_generation_journey
from tests.test_use_case_claim_bound_installed import _applied, _installed
from tests.test_use_case_claim_connected import LOADER
from tests.test_use_case_claim_host import PROFILE, _expected


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='M connected generation needs Linux x86-64 CPython 3.13')
MEMBERS = ('support.json', 'audit.json', 'claim.json')


def _install(tmp_path: Path, index: int, version: str, task: str,
             wheelhouse: Path, rows: list[dict], requirements: list[dict]):
    environments = tmp_path / f'environments-{index}'
    environments.mkdir(mode=0o700)
    host = _applied(tmp_path, f'bound-m-{index}', version, LOADER, generation_task=task)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
        requirements, environments, f'package-m-{index}')
    return host, install_plan, receipt


def _layout(folder: Path, task: str) -> dict:
    (folder / task).mkdir(mode=0o700)
    ready, release = folder / 'ready.txt', folder / 'release.txt'
    return {'environment': {'M_EFFECT_DIRECTORY': str(folder), 'M_READY_PATH': str(ready),
                            'M_RELEASE_PATH': str(release), 'M_HOLD': '1',
                            'M_TASKS': 'two', 'M_CLAIM_SCENARIO': 'accept',
                            'M_APPROVAL': '1'},
            'ready': ready, 'release': release,
            'effects': [(folder / task / member, raw)
                        for member, raw in zip(MEMBERS, _expected(task))]}


def _verify(layout: dict, task: str) -> None:
    support, audit, claim = (path.read_bytes() for path, _ in layout['effects'])
    released = json.loads(claim)
    assert released['task_id'] == task and released['status'] == 'released'
    assert released['claim'] == 'Permit is active'
    assert released['support_sha256'] == hashlib.sha256(support).hexdigest()
    assert released['audit_sha256'] == hashlib.sha256(audit).hexdigest()
    cited = json.loads(support)
    assert cited['source_id'] == 'fixture-permit-register-v1'
    assert cited['quote'] == 'Permit is active' and cited['decision'] == 'supported'
    assert json.loads(audit)['task_id'] == task


JOURNEY = GenerationJourney(
    host_profile='claim-m-v1', package='claim_host',
    reference_name='M_CONNECTED_REF', public_name='M_AUTH_PUBKEY_FILE',
    release_name='M_RELEASE_PATH', tasks=('claim-one', 'claim-two'),
    preferred_label='supported',
    other_profiles=('retrieval-d-v1', 'retention-h-v1', 'graph-l-v1', 'completion-e-v1'),
    install=_install, layout=_layout, verify=_verify)


def test_bound_m_connected_upgrade_and_retained_rollback(tmp_path, monkeypatch):
    from tests.test_connected_generation_graph_installed import JOURNEY as graph
    result = run_generation_journey(tmp_path, monkeypatch, replace(JOURNEY, foreign=graph))
    assert result['calls'] == 2
