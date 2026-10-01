"""Two freshly bound L hosts share one installed synthetic connected ledger."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from tests.connected_generation_journey import GenerationJourney, run_generation_journey
from tests.test_use_case_graph_bind import PROFILE
from tests.test_use_case_graph_bound_installed import _applied, _installed
from tests.test_use_case_graph_connected import LOADER
from tests.test_use_case_graph_installed import _database_readback, _expected


pytestmark = pytest.mark.skipif(
    not PROFILE, reason='L connected generation needs Linux x86-64 CPython 3.13')


def _install(tmp_path: Path, index: int, version: str, task: str,
             wheelhouse: Path, rows: list[dict], requirements: list[dict]):
    environments = tmp_path / f'environments-{index}'
    environments.mkdir(mode=0o700)
    host = _applied(tmp_path, f'bound-l-{index}', version, LOADER, generation_task=task)
    install_plan, receipt = _installed(tmp_path, host, wheelhouse, rows,
        requirements, environments, f'package-l-{index}')
    return host, install_plan, receipt


def _raw(task: str) -> bytes:
    effect = json.loads(_expected())
    effect['task_id'] = task
    return (json.dumps(effect, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _layout(folder: Path, task: str) -> dict:
    effect, ready, release = folder / (task + '.json'), folder / 'ready.txt', \
        folder / 'release.txt'
    return {'environment': {'GRAPH_DB_PATH': str(folder / 'graph.sqlite'),
                            'GRAPH_EFFECT_PATH': str(effect),
                            'GRAPH_READY_PATH': str(ready), 'L_TASKS': 'two',
                            'L_HOLD': '1', 'L_RELEASE_PATH': str(release),
                            'L_APPROVAL': '1', 'L_EXPECTED_REVISION': '0'},
            'ready': ready, 'release': release, 'effects': [(effect, _raw(task))]}


def _verify(layout: dict, task: str) -> None:
    effect, raw = layout['effects'][-1]
    merged = json.loads(effect.read_bytes())
    assert merged['task_id'] == task and merged['revision'] == 1
    assert merged['receipt'] == {'left_key': 'left', 'right_key': 'right',
        'sources': ['registry-left', 'registry-right'],
        'revision_before': 0, 'revision_after': 1}
    assert merged['merges'] == merged['audits'] == [merged['receipt']]
    # The host-owned SQLite graph is read by a separate read-only connection.
    _database_readback(effect.parent / 'graph.sqlite', raw)


JOURNEY = GenerationJourney(
    host_profile='graph-l-v1', package='graph_host',
    reference_name='L_CONNECTED_REF', public_name='L_AUTH_PUBKEY_FILE',
    release_name='L_RELEASE_PATH', tasks=('graph-one', 'graph-two'),
    preferred_label='same',
    other_profiles=('retrieval-d-v1', 'retention-h-v1', 'claim-m-v1', 'completion-e-v1'),
    install=_install, layout=_layout, verify=_verify)


def test_bound_l_connected_upgrade_and_retained_rollback(tmp_path, monkeypatch):
    from tests.test_connected_generation_claim_installed import JOURNEY as claim
    result = run_generation_journey(tmp_path, monkeypatch, replace(JOURNEY, foreign=claim))
    assert result['calls'] == 2
