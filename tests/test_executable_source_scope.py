"""A parsed name is not necessarily the module symbol with the same spelling."""
import ast

import pytest

from jev_integration_evaluator.integrations.lifecycle import plan_implementation
from jev_integration_evaluator.io import InputError
from scripts.implementation_fixtures import fixture
from test_executable_safety import refreshed, snapshots


@pytest.mark.parametrize('binding', ['runtime', 'evidence', 'registry', 'gate', 'validate', 'blocked', 'guard', 'baseline_action', 'original'])
def test_parameter_shadowing_required_module_symbol_is_unsupported(tmp_path, binding):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C')
    path = root / spec['source']['file']
    text = path.read_text()
    parameter = 'legacy_dispatch_scenario_c' if binding == 'original' else spec['bindings'][binding]
    text = text.replace('def '+spec['source']['symbol']+'(payload):',
                        'def '+spec['source']['symbol']+'('+parameter+'):')
    text = text.replace('return legacy_dispatch_scenario_c(payload)',
                        'return legacy_dispatch_scenario_c('+parameter+')')
    path.write_text(text)
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    bundle = tmp_path / 'bundle'
    with pytest.raises(InputError, match='shadow'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == before and not bundle.exists()


@pytest.mark.parametrize('kind', ['exception', 'match_as', 'match_star', 'match_mapping'])
def test_capture_assignments_make_module_binding_ambiguous(tmp_path, kind):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C')
    path = root / spec['source']['file']
    name = spec['bindings']['runtime']
    additions = {
        'exception': '\ntry:\n    raise ValueError()\nexcept ValueError as '+name+':\n    pass\n',
        'match_as': '\nmatch 1:\n    case '+name+':\n        pass\n',
        'match_star': '\nmatch [1]:\n    case [*'+name+']:\n        pass\n',
        'match_mapping': '\nmatch {}:\n    case {**'+name+'}:\n        pass\n',
    }
    path.write_text(path.read_text()+additions[kind])
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    bundle = tmp_path / 'bundle'
    with pytest.raises(InputError, match='ambiguous'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == before and not bundle.exists()


@pytest.mark.parametrize('kind', [
    'function_default', 'keyword_default', 'async_default',
    'function_decorator', 'async_decorator', 'class_decorator',
    'class_base', 'class_keyword',
])
def test_definition_time_rebinding_is_rejected_without_importing_target(tmp_path, kind):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C')
    path = root / spec['source']['file']
    name = spec['bindings']['runtime']
    definitions = {
        'function_default': f'def unrelated(value=({name} := None)):\n    return value\n',
        'keyword_default': f'def unrelated(*, value=({name} := None)):\n    return value\n',
        'async_default': f'async def unrelated(value=({name} := None)):\n    return value\n',
        'function_decorator': f'@({name} := (lambda value: value))\ndef unrelated(value):\n    return value\n',
        'async_decorator': f'@({name} := (lambda value: value))\nasync def unrelated(value):\n    return value\n',
        'class_decorator': f'@({name} := (lambda value: value))\nclass Unrelated:\n    pass\n',
        'class_base': f'class Unrelated(({name} := object)):\n    pass\n',
        'class_keyword': f'class Unrelated(metaclass=({name} := type)):\n    pass\n',
    }
    path.write_text(path.read_text()+'\n'+definitions[kind]+
                    '\nraise AssertionError("Planning must not import this target")\n')
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    bundle = tmp_path / 'bundle'
    with pytest.raises(InputError, match='ambiguous'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == before and not bundle.exists()


def test_unrelated_function_and_class_bodies_do_not_rebind_module_symbols(tmp_path):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C')
    path = root / spec['source']['file']
    name = spec['bindings']['runtime']
    path.write_text(path.read_text()+f'\ndef unrelated():\n    {name} = None\n'
                    f'\nasync def unrelated_async():\n    {name} = None\n'
                    f'\nclass Unrelated:\n    {name} = None\n'
                    f'\ndef unrelated_default(value=lambda: ({name} := None)):\n    return value\n'
                    '\nraise AssertionError("Planning must not import this target")\n')
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    result = plan_implementation(root, inventory, spec['candidate_id'], spec, tmp_path/'bundle')
    assert result['status'] == 'planned' and result['target_executed'] is False
    assert snapshots(root) == before


@pytest.mark.parametrize('parameter', ['OPTIONS', 'dict', 'perform_primary_scenario_c'])
def test_registry_local_names_are_not_inferred_as_module_bindings(tmp_path, parameter):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'C')
    path = root / spec['source']['file']
    text = path.read_text().replace('def '+spec['bindings']['registry']+'(request):',
                                    'def '+spec['bindings']['registry']+'('+parameter+'):')
    if parameter.startswith('perform_'):
        text = text.replace('return dict(OPTIONS)',
                            "return {'base': perform_primary_scenario_c, 'alt': perform_alternative_scenario_c}")
    path.write_text(text)
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    bundle = tmp_path / 'bundle'
    with pytest.raises(InputError, match='shadow'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == before and not bundle.exists()


def test_postaction_executor_name_must_not_resolve_to_parameter(tmp_path):
    root = tmp_path / 'target'
    inventory, spec = fixture(root, 'E')
    path = root / spec['source']['file']
    text = path.read_text().replace('def legacy_dispatch_scenario_e(request):',
                                    'def legacy_dispatch_scenario_e(perform_primary_scenario_e):')
    text = text.replace('return perform_primary_scenario_e(request)',
                        'return perform_primary_scenario_e(perform_primary_scenario_e)')
    path.write_text(text)
    inventory, spec = refreshed(root, spec)
    before = snapshots(root)
    bundle = tmp_path / 'bundle'
    with pytest.raises(InputError, match='shadow'):
        plan_implementation(root, inventory, spec['candidate_id'], spec, bundle)
    assert snapshots(root) == before and not bundle.exists()
