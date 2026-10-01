"""Timeout diagnostics retain InputError compatibility and omit provider text."""
import io
import json
import urllib.error

import pytest

from jev_integration_evaluator.client import EvaluationTimeoutError, TypeSafeHTTPClient
from jev_integration_evaluator.io import InputError


@pytest.mark.parametrize('failure,timeout', [
    (TimeoutError('sensitive transport detail'), True),
    (urllib.error.URLError(TimeoutError('sensitive transport detail')), True),
    (urllib.error.URLError('sensitive transport detail'), False),
    (OSError('sensitive transport detail'), False),
])
def test_only_transport_timeouts_receive_specific_safe_type(monkeypatch, failure, timeout):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-test-reference')
    client = TypeSafeHTTPClient(allow_network=True)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(client.opener, 'open', fail)
    with pytest.raises(InputError) as raised:
        client.evaluate('synthetic state', {'q': {'type': 'noul', 'instructions': 'Is this synthetic?'}}, 'jev-1.13.0', 10)
    assert isinstance(raised.value, EvaluationTimeoutError) is timeout
    assert str(raised.value) == 'TypeSafe transport failed or timed out'
    assert raised.value.__suppress_context__


def test_late_transport_response_is_timeout_without_using_result(monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-test-reference')
    client = TypeSafeHTTPClient(allow_network=True)
    payload = json.dumps({'model': 'jev-1.13.0',
        'answers': {'q': {'type': 'noul', 'noul': 1}},
        'usage': {'input_tokens': 1, 'output_tokens': 1}}).encode()
    monkeypatch.setattr(client.opener, 'open', lambda *args, **kwargs: io.BytesIO(payload))
    ticks = iter((1.0, 1.02))
    monkeypatch.setattr('jev_integration_evaluator.client.time.monotonic', lambda: next(ticks))
    with pytest.raises(EvaluationTimeoutError, match='exceeded latency budget'):
        client.evaluate('synthetic state', {'q': {'type': 'noul', 'instructions': 'Is this synthetic?'}}, 'jev-1.13.0', 10)
