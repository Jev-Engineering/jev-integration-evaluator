"""Aggregator contract tests with explicit provenance doubles, no installation."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from jev_integration_evaluator import template_connected_packages_binding as packages
from jev_integration_evaluator.contracts import validate_contract
from jev_integration_evaluator.io import digest, file_hash, read_json


def _member(root: Path, name: str) -> dict:
    site = root / name
    site.mkdir(mode=0o700)
    origins = {}
    for role in ('host', 'adapter', 'console', 'loader'):
        path = site / (role + '.py')
        path.write_bytes(b'# provenance double only\n')
        origins[role] = {'path': str(path), 'sha256': file_hash(path),
                         'wheel_member': name + '/' + role + '.py'}
    project = site / 'pyproject.toml'
    project.write_bytes(b'# provenance double only\n')
    schema = read_json(Path(__file__).resolve().parents[1] /
                       'schemas/connected-installed-binding-v1.schema.json')
    result = {key: 'a' * 64 for key in schema['required'] if key.endswith('_sha256')}
    result.update(schema_version='1.0', kind='connected-installed-binding-v1',
        candidate_id=name, site=str(site), source_file=name + '/host.py', origins=origins,
        reviewed_project_path=str(project), reviewed_project_sha256=file_hash(project),
        source_plan={'files': [{'path': row['path'], 'sha256': row['sha256']}
                               for row in origins.values()] +
                              [{'path': str(project), 'sha256': file_hash(project)}]})
    result['binding_sha256'] = digest({key: value for key, value in result.items()
                                      if key != 'binding_sha256'})
    validate_contract(result, 'connected-installed-binding-v1')
    return result


def _input(name: str) -> dict:
    return {'package_plan': {'project_name': name, 'project_version': '1.0.0'},
            'package_receipt': {}, 'install_plan': {},
            'install_receipt': {'installed': {'distributions': {
                name: '1.0.0', 'jev-integration-evaluator': '1.3.0.dev12',
                'PyYAML': '6.0.3', 'jsonschema': '4.26.0'}}},
            'trusted_package_receipt_sha256': 'b' * 64,
            'trusted_install_receipt_sha256': 'c' * 64}


def test_packages_aggregator_uses_actual_host_distribution_not_runtime_dependencies(tmp_path, monkeypatch):
    from jev_integration_evaluator import template_packages_records
    monkeypatch.setattr(template_packages_records, 'installed_records_snapshot', lambda *_values: {})
    monkeypatch.setattr(packages, '_member_import_plan', lambda *_values: [])
    members = {name: _member(tmp_path, name) for name in ('alpha', 'queue')}
    seen = []
    def provenance(**values):
        seen.append(values)
        return members[values['package_plan']['project_name']]
    monkeypatch.setattr(packages, 'derive_installed_binding', provenance)
    inputs = [_input('alpha'), _input('queue')]
    report = packages.derive_installed_packages_binding(inputs, source_root=str(tmp_path))
    assert seen == inputs
    assert report['candidate_ids'] == ['alpha', 'queue']
    assert report['members'] == members
    assert set(report['distributions']) == {'alpha', 'queue'}
    assert len(report['source_plan']['files']) == 10
    assert digest({key: value for key, value in report.items()
                   if key != 'binding_sha256'}) == report['binding_sha256']


@pytest.mark.parametrize('changed', ['distribution', 'candidate', 'site', 'outside', 'missing_loader'])
def test_packages_aggregator_refuses_ambiguous_or_outside_generations(tmp_path, monkeypatch, changed):
    from jev_integration_evaluator import template_packages_records
    monkeypatch.setattr(template_packages_records, 'installed_records_snapshot', lambda *_values: {})
    monkeypatch.setattr(packages, '_member_import_plan', lambda *_values: [])
    members = [_member(tmp_path, 'alpha'), _member(tmp_path, 'queue')]
    inputs = [_input('alpha'), _input('queue')]
    if changed == 'distribution':
        inputs[1] = _input('alpha')
    elif changed == 'candidate':
        members[1]['candidate_id'] = 'alpha'
    elif changed == 'site':
        members[1]['site'] = members[0]['site']
    elif changed == 'outside':
        outside = tmp_path.parent / (tmp_path.name + '-outside')
        outside.mkdir(mode=0o700)
        members[1] = _member(outside, 'outside')
    else:
        del members[1]['origins']['loader']
    returned = iter(deepcopy(members))
    monkeypatch.setattr(packages, 'derive_installed_binding', lambda **_values: next(returned))
    with pytest.raises(packages.PackagesConnectedBindingError):
        packages.derive_installed_packages_binding(inputs, source_root=str(tmp_path))


@pytest.mark.parametrize('race', ['missing_origin', 'root_stat'])
def test_packages_aggregator_redacts_missing_or_racing_filesystem(tmp_path, monkeypatch, race):
    from jev_integration_evaluator import template_packages_records
    monkeypatch.setattr(template_packages_records, 'installed_records_snapshot', lambda *_values: {})
    monkeypatch.setattr(packages, '_member_import_plan', lambda *_values: [])
    members = [_member(tmp_path, 'alpha'), _member(tmp_path, 'queue')]
    if race == 'missing_origin':
        Path(members[1]['origins']['host']['path']).unlink()
    else:
        original_stat = Path.stat
        def racing_stat(path, *args, **kwargs):
            if path == tmp_path:
                raise OSError('private/path/that/must/not/be/printed')
            return original_stat(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'stat', racing_stat)
    returned = iter(members)
    monkeypatch.setattr(packages, 'derive_installed_binding', lambda **_values: next(returned))
    with pytest.raises(packages.PackagesConnectedBindingError) as refused:
        packages.derive_installed_packages_binding([_input('alpha'), _input('queue')],
                                                  source_root=str(tmp_path))
    assert str(refused.value) == 'packages_connected_provenance_unavailable'
    assert refused.value.__cause__ is None
