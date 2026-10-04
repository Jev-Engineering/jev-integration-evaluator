"""Authored local protocol fixture validation; no real provider or network."""
import copy
import shutil

import pytest

from jev_integration_evaluator.client import validate_response
from jev_integration_evaluator.io import InputError
from tests.connected_generation_journey import synthetic_typed_answers


@pytest.mark.parametrize('name', ['registered_alpha_connected', 'work_queue'])
def test_owner_fixture_declares_deadline_before_source_review_and_preserves_defaults(tmp_path, name):
    import importlib
    fixture = importlib.import_module('tests.independent_hosts.' + name + '.qualification')
    host = tmp_path / name
    shutil.copytree(fixture.ROOT, host, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    ordinary, _ = fixture.source_matched_request(host)
    owned, _ = fixture.source_matched_request(host, runtime_timeout_ms=10_000)
    original = ordinary['implementation_spec']
    revised = owned['implementation_spec']
    assert original['runtime']['configuration']['timeout_ms'] == 2000
    assert revised['runtime']['configuration']['timeout_ms'] == 10_000
    for field in ('source', 'recipe', 'questions', 'primary_question', 'evidence_question', 'label_actions'):
        assert revised[field] == original[field]
    expected = copy.deepcopy(original['runtime'])
    expected['configuration']['timeout_ms'] = 10_000
    assert revised['runtime'] == expected
    again, _ = fixture.source_matched_request(host)
    assert again['implementation_spec']['runtime']['configuration']['timeout_ms'] == 2000
    with pytest.raises(InputError, match='^offline_owner_fixture_timeout_not_supported$'):
        fixture.source_matched_request(host, runtime_timeout_ms=10_001)


def test_existing_local_choice_noul_wire_shape_is_validated():
    questions = {
        'decision': {'type': 'choice', 'instructions': {'question': 'Synthetic fixture choice'},
                     'criteria': {'baseline': 'Fixture baseline', 'alternative': 'Fixture alternative'}},
        'evidence': {'type': 'noul', 'instructions': {'question': 'Synthetic fixture evidence adequate?'},
                     'criteria': {'true': 'Fixture adequate', 'false': 'Fixture inadequate'}},
    }
    response = {'model': 'jev-1.13.0', 'answers': synthetic_typed_answers(questions, 'alternative'),
                'usage': {'input_tokens': 1, 'output_tokens': 1}}
    assert validate_response(response, questions, 'jev-1.13.0') == response
    for name, wrong in (
            ('decision', {'type': 'choice', 'value': 'alternative', 'confidence': 1.0,
                          'probabilities': {'baseline': 0.0, 'alternative': 1.0}}),
            ('evidence', {'type': 'noul', 'value': True, 'confidence': 1.0})):
        invalid = copy.deepcopy(response)
        invalid['answers'][name] = wrong
        with pytest.raises(InputError):
            validate_response(invalid, questions, 'jev-1.13.0')
