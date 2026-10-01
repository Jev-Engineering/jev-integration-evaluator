"""Two freshly bound E hosts share one installed synthetic connected ledger."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from tests.connected_generation_journey import GenerationJourney, run_generation_journey
from tests.test_reusable_templates import fixture_module
from tests.test_use_case_completion_connected import LOADER, _installed
from tests.test_use_case_completion_host import PROFILE, _applied, _expected


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='E connected generation needs Linux x86-64 CPython 3.13')
TASKS = ('completion-one', 'completion-two')


def _install(tmp_path: Path, index: int, version: str, task: str,
             wheelhouse: Path, rows: list[dict], requirements: list[dict]):
    # The E installer helper owns one package and environment parent per root.
    root = tmp_path / f'bound-e-{index}'
    root.mkdir(mode=0o700)
    host = _applied(root, 'host', version, TASKS, LOADER, generation_task=task)
    install_plan, receipt = _installed(root, host, wheelhouse)
    assert install_plan['package_plan']['request']['wheels'] == rows
    assert install_plan['package_plan']['request']['requirements'] == requirements
    return host, install_plan, receipt


def _layout(folder: Path, task: str) -> dict:
    ready, release = folder / 'ready.txt', folder / 'release.txt'
    state, receipt = _expected(task)
    return {'environment': {'E_RAW_STATE_TEMPLATE': str(folder / 'state-{task_id}.json'),
                            'E_EFFECT_RECEIPT_TEMPLATE': str(folder / 'receipt-{task_id}.json'),
                            'E_READY_PATH': str(ready), 'E_TASKS': 'two',
                            'E_HOLD': '1', 'E_RELEASE_PATH': str(release)},
            'ready': ready, 'release': release,
            'effects': [(folder / f'state-{task}.json', state),
                        (folder / f'receipt-{task}.json', receipt)]}


def _verify(layout: dict, task: str) -> None:
    (state_path, _), (receipt_path, _) = layout['effects']
    state, receipt = state_path.read_bytes(), json.loads(receipt_path.read_bytes())
    oracle = fixture_module('examples/coding-agent/completion_oracle.py',
                            'generation_e_oracle')
    objective = {'task_id': task, 'allowed_fields': ['task_id', 'status', 'revision',
                 'labels', 'unrequested'], 'required_status': 'closed',
                 'required_labels': ['verified'], 'required_unrequested': []}
    assert oracle.exact_goal(json.loads(state), objective)
    assert not oracle.exact_goal({**json.loads(state), 'labels': []}, objective)
    assert receipt['task_id'] == task and receipt['operation'] == 'close_and_label'
    assert receipt['after_sha256'] == hashlib.sha256(state).hexdigest()


JOURNEY = GenerationJourney(
    host_profile='completion-e-v1', package='completion_host',
    reference_name='E_CONNECTED_REF', public_name='E_AUTH_PUBKEY_FILE',
    release_name='E_RELEASE_PATH', tasks=TASKS, preferred_label=None,
    other_profiles=('retrieval-d-v1', 'retention-h-v1', 'graph-l-v1', 'claim-m-v1'),
    install=_install, layout=_layout, verify=_verify)


def test_bound_e_connected_upgrade_and_retained_rollback(tmp_path, monkeypatch):
    from tests.test_connected_generation_graph_installed import JOURNEY as graph
    result = run_generation_journey(tmp_path, monkeypatch, replace(JOURNEY, foreign=graph))
    assert result['calls'] == 2
