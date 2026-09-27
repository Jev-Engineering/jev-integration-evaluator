"""Host assertions and model responses here are synthetic, never deployment receipts."""
import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import threading
import pytest
from jev_integration_evaluator.io import InputError, digest, read_jsonl
from jev_integration_evaluator.runtime import SafeRouter, Thresholds
from jev_integration_evaluator.robustness import request_fingerprint
from jev_integration_evaluator.traces import AuditLog, verify_log
from test_runtime_client import Client, activation, kwargs


def receipt(config, event):
    now = datetime.now(timezone.utc)
    return {**activation(config, event), 'activation_id': 'synthetic-unit-test', 'evidence_type': 'observed',
            'issued_at': (now - timedelta(minutes=1)).isoformat(),
            'expires_at': (now + timedelta(minutes=1)).isoformat(),
            'ordered_questions_hash': request_fingerprint(None, event['questions'], config['model'])}


@pytest.mark.parametrize('field', ['probability_floor', 'confidence_floor', 'inspect_probability_floor', 'evidence_yes_floor'])
def test_action_threshold_cannot_weaken_global(cfg, response, field):
    values = asdict(Thresholds()); values[field] -= .01
    with pytest.raises(InputError):
        SafeRouter(Client(response), cfg['runtime'], action_thresholds={'inspect': Thresholds(**values)})


def test_action_specific_floor_is_applied_and_hash_bound(cfg, example_event, response):
    c = cfg['runtime']; c['mode'] = 'active'
    limits = {'inspect': Thresholds(probability_floor=.999)}
    a = activation(c, example_event)
    client = Client(response)
    with SafeRouter(client, c, activation=a, action_thresholds=limits) as r:
        assert r.route(**kwargs(example_event)).reason == 'activation_or_calibration_missing'
    assert client.calls == 0
    a['action_thresholds_hash'] = digest({k: asdict(v) for k, v in limits.items()})
    with SafeRouter(client, c, activation=a, action_thresholds=limits) as r:
        decision = r.route(**kwargs(example_event))
        assert decision.source == 'policy' and decision.reason == 'gather_more_evidence'
    assert client.calls == 1


@pytest.mark.parametrize('mutation', ['expired', 'future', 'timezone', 'missing_expiry', 'synthetic', 'id', 'order', 'revoked'])
def test_strict_activation_rejects_invalid_receipts(cfg, example_event, response, mutation):
    c = cfg['runtime']; c['mode'] = 'active'; a = receipt(c, example_event)
    if mutation == 'expired': a['expires_at'] = '2000-01-01T00:00:00+00:00'
    if mutation == 'future': a['issued_at'] = '2100-01-01T00:00:00+00:00'
    if mutation == 'timezone': a['expires_at'] = '2100-01-01T00:00:00'
    if mutation == 'missing_expiry': del a['expires_at']
    if mutation == 'synthetic': a['evidence_type'] = 'synthetic'
    if mutation == 'id': a['activation_id'] = ''
    if mutation == 'order': a['ordered_questions_hash'] = '0' * 64
    if mutation == 'revoked': a['revoked'] = True
    client = Client(response)
    with SafeRouter(client, c, activation=a, require_expiring_activation=True) as r:
        assert r.route(**kwargs(example_event)).source == 'baseline'
    assert client.calls == 0


def test_valid_strict_receipt_and_revoke(cfg, example_event, response):
    c = cfg['runtime']; c.update(mode='active', cache_ttl_s=60)
    client = Client(response)
    with SafeRouter(client, c, activation=receipt(c, example_event), require_expiring_activation=True) as r:
        assert r.route(**kwargs(example_event, immutable_state=True, cache_scope='unit')).source == 'jev_assessment'
        assert r.cache
        r.revoke_activation()
        assert not r.cache
        assert r.route(**kwargs(example_event)).reason == 'runtime_suspended'
    assert client.calls == 1


@pytest.mark.parametrize('operation', ['suspend', 'revoke_activation', 'expiry'])
def test_late_inflight_result_cannot_survive_suspension(cfg, example_event, response, operation):
    started = threading.Event(); release = threading.Event(); result = []
    class BlockingClient(Client):
        def evaluate(self, *args):
            started.set()
            assert release.wait(3)
            return copy.deepcopy(self.response)
    c = cfg['runtime']; c.update(mode='active', timeout_ms=5000)
    client = BlockingClient(response)
    with SafeRouter(client, c, activation=receipt(c, example_event), require_expiring_activation=True) as r:
        thread = threading.Thread(target=lambda: result.append(r.route(**kwargs(example_event))))
        thread.start()
        try:
            assert started.wait(3)
            if operation == 'expiry': r.activation['expires_at'] = '2000-01-01T00:00:00+00:00'
            else: getattr(r, operation)()
        finally:
            release.set(); thread.join(5)
        assert not thread.is_alive()
        assert result[0].source == 'baseline' and result[0].action == 'stop'


def test_cache_tracks_order_and_receipt_is_immutable_copy(cfg, example_event, response):
    c = cfg['runtime']; c.update(mode='active', cache_ttl_s=60)
    client = Client(response); a = activation(c, example_event)
    with SafeRouter(client, c, activation=a) as r:
        a['approved'] = False
        args = kwargs(example_event, immutable_state=True, cache_scope='unit')
        assert r.route(**args).source == 'jev_assessment'
        q = copy.deepcopy(example_event['questions'])
        q['action']['criteria'] = dict(reversed(list(q['action']['criteria'].items())))
        assert r.route(**{**args, 'questions': q}).source == 'jev_assessment'
    assert client.calls == 2  # Canonical questions hash remains legacy-compatible; cache must not.


def test_checkpoint_detects_valid_chain_truncation(tmp_path):
    path = tmp_path / 'audit.jsonl'
    log = AuditLog(path)
    for i in range(3): log.append({'type': 'fixture', 'index': i})
    rows = read_jsonl(path)
    plain = verify_log(rows)
    expected = rows[-1]['event_hash']
    assert verify_log(rows, expected_final_hash=expected, expected_events=3)['truncation_checked']
    # A self-consistent prefix passes ordinary chain checking, not the external checkpoint.
    verify_log(rows[:2])
    with pytest.raises(InputError): verify_log(rows[:2], expected_final_hash=expected)
    with pytest.raises(InputError): verify_log(rows[:2], expected_events=3)


@pytest.mark.parametrize('values', [{'expected_events': True}, {'expected_events': -1}, {'expected_final_hash': 'bad'}])
def test_checkpoint_invalid_contract(values):
    with pytest.raises(InputError): verify_log([], **values)
