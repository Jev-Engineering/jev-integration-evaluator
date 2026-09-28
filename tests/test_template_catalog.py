"""Source-bound template rendering from independently authored example hosts."""
import copy
from pathlib import Path

import pytest

from jev_integration_evaluator.io import InputError, digest, file_hash, read_json
from jev_integration_evaluator.template_catalog import (
    inspect_template, list_templates, materialize_template, render_status,
    template_error, validate_template_request,
)
from jev_integration_evaluator.integrations.lifecycle import plan_implementation

ROOT = Path(__file__).resolve().parents[1]


def example(letter):
    directory = ROOT / 'examples' / 'implementation' / letter
    return directory / 'target', {
        'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
        'template_version': '1.0.0', 'backend': 'python',
        'profile': 'module-tail-call-v1',
        'reviewed_inventory': read_json(directory / 'reviewed-inventory.example.json'),
        'implementation_spec': read_json(directory / 'binding.example.json'),
    }


@pytest.mark.parametrize('letter', ['a', 'c'])
def test_two_authored_hosts_render_same_template_without_target_changes(tmp_path, letter):
    root, request = example(letter)
    before = {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    validated = validate_template_request(root, request)
    first = materialize_template(root, request, tmp_path / 'first')
    second = materialize_template(root, request, tmp_path / 'second')
    assert first == second
    assert first['request_sha256'] == digest(request)
    assert first['source_sha256'] == request['implementation_spec']['source']['source_sha256']
    assert first['lifecycle']['apply'] == 'pending_separate_approval'
    assert first['lifecycle']['measured_benefit'] == 'unknown'
    assert validated['policy_sha256'] == first['policy_sha256']
    assert {p.name: file_hash(p) for p in root.iterdir() if p.is_file()} == before
    assert read_json(tmp_path / 'first' / 'render-status.json')['status'] == 'complete'
    assert all(file_hash(tmp_path / 'first' / name) == expected
               for name, expected in first['owned_resources'].items())
    planned = plan_implementation(root,
        read_json(tmp_path / 'first' / 'reviewed-inventory.json'), first['candidate_id'],
        read_json(tmp_path / 'first' / 'implementation-spec.json'), tmp_path / 'planner-bundle')
    assert planned['status'] == 'planned'
    assert planned['target_modified'] is False


def test_packaged_catalog_and_strict_versions(tmp_path):
    listing = list_templates()
    assert listing['templates'][0]['manifest_sha256'] == inspect_template('python.bounded-tail-call')['manifest_sha256']
    assert inspect_template('python.bounded-tail-call')['recipe_versions']['python.C'] == '1.0'
    with pytest.raises(InputError, match='Unsupported template'):
        inspect_template('python.bounded-tail-call', '0.9.0')
    root, request = example('c')
    for mutation in ({'template_version': '0.9.0'}, {'profile': 'class-method-v1'},
                     {'backend': 'javascript'}, {'unknown': True}, {'schema_version': '0.9'}):
        invalid = copy.deepcopy(request); invalid.update(mutation)
        with pytest.raises(InputError): validate_template_request(root, invalid)
    assert not list(tmp_path.iterdir())


def test_stale_source_and_policy_binding(tmp_path):
    root, request = example('c')
    copied = tmp_path / 'host'; copied.mkdir()
    for source in root.iterdir():
        if source.is_file(): (copied / source.name).write_bytes(source.read_bytes())
    original = validate_template_request(copied, request)
    changed = copy.deepcopy(request)
    changed['implementation_spec']['runtime']['configuration']['timeout_ms'] = 1900
    updated = validate_template_request(copied, changed)
    assert updated['policy_sha256'] != original['policy_sha256']
    selected = request['implementation_spec']['source']['file']
    with (copied / selected).open('ab') as handle: handle.write(b'\n# drift\n')
    with pytest.raises(InputError, match='drift|changed'):
        materialize_template(copied, request, tmp_path / 'render')
    assert not (tmp_path / 'render').exists()


def test_collision_traversal_and_interrupted_render(tmp_path, monkeypatch):
    root, request = example('c')
    output = tmp_path / 'render'
    materialize_template(root, request, output)
    with pytest.raises(InputError, match='collision: marker_complete_unverified'):
        materialize_template(root, request, output)
    with pytest.raises(InputError, match='outside'):
        materialize_template(root, request, root / 'inside')
    from jev_integration_evaluator import template_catalog as catalog
    real_write = catalog.write_json
    def interrupted(path, value):
        if path.name == 'implementation-spec.json': raise KeyboardInterrupt('simulated process loss')
        return real_write(path, value)
    monkeypatch.setattr(catalog, 'write_json', interrupted)
    with pytest.raises(KeyboardInterrupt): materialize_template(root, request, tmp_path / 'interrupted')
    assert read_json(tmp_path / 'interrupted' / 'render-status.json')['status'] == 'incomplete'
    with pytest.raises(InputError, match='collision: incomplete'):
        materialize_template(root, request, tmp_path / 'interrupted')


def test_first_marker_interruption_is_classified_without_reuse(tmp_path, monkeypatch):
    root, request = example('c')
    from jev_integration_evaluator import template_catalog as catalog
    def interrupted(path, value):
        raise KeyboardInterrupt('before first marker')
    monkeypatch.setattr(catalog, 'write_json', interrupted)
    output = tmp_path / 'markerless'
    with pytest.raises(KeyboardInterrupt): materialize_template(root, request, output)
    assert render_status(output) == {'schema_version': '1.0', 'status': 'incomplete_unmarked'}
    with pytest.raises(InputError, match='collision: incomplete_unmarked'):
        materialize_template(root, request, output)


def test_read_only_preflight_rejects_occupied_adapter_and_actual_unsupported_ast(tmp_path):
    from scripts.implementation_fixtures import fixture
    from jev_integration_evaluator.config import load_config
    from jev_integration_evaluator.scanner import scan_repo
    from jev_integration_evaluator.scoring import apply_reviews
    root = tmp_path / 'host'
    inventory, spec = fixture(root, 'C', tag='template_preflight')
    request = {'schema_version': '1.0', 'template_id': 'python.bounded-tail-call',
               'template_version': '1.0.0', 'backend': 'python',
               'profile': 'module-tail-call-v1', 'reviewed_inventory': inventory,
               'implementation_spec': spec}
    adapter = root / (spec['output']['module'] + '.py')
    adapter.write_text('# occupied\n', encoding='utf-8')
    with pytest.raises(InputError, match='output already exists'):
        materialize_template(root, request, tmp_path / 'collision-output')
    assert not (tmp_path / 'collision-output').exists()
    adapter.unlink()
    selected = root / spec['source']['file']
    source = selected.read_text(encoding='utf-8')
    # The selected tail call is the legacy dispatch.
    line = next(line for line in source.splitlines() if line.strip().startswith('return legacy_dispatch_'))
    selected.write_text(source.replace(line, '    result = ' + line.strip()[7:] + '\n    return result'), encoding='utf-8')
    cfg = load_config(); cfg['repository']['typescript_ast'] = False
    refreshed = scan_repo(root, cfg)
    candidate = next(c for c in refreshed['candidates'] if c['source']['symbol'] == spec['source']['symbol'])
    from jev_integration_evaluator.integrations.recipes import anchor_hash
    import ast
    statement = next(n for n in ast.parse(selected.read_text(encoding='utf-8')).body
                     if isinstance(n, ast.FunctionDef) and n.name == spec['source']['symbol']).body[-1]
    source_record = candidate['source']
    apply_reviews(refreshed, {candidate['candidate_id']: {
        'source_sha256': source_record['source_sha256'], 'approved': True,
        'reviewer': 'offline-test-review', 'reason': 'Synthetic source-specific review'}}, cfg)
    spec['candidate_id'] = candidate['candidate_id']
    spec['experiment_id'] = candidate['recommended_experiment']['id']
    spec['inventory_sha256'] = digest(refreshed)
    spec['inventory_fingerprint'] = refreshed['scan_fingerprint']
    spec['source'].update(file_sha256=source_record['file_sha256'],
                          source_sha256=source_record['source_sha256'],
                          anchor_sha256=anchor_hash(statement))
    spec['binding_review']['source_sha256'] = source_record['source_sha256']
    request['reviewed_inventory'] = refreshed
    with pytest.raises(InputError, match='Unsupported source shape'):
        materialize_template(root, request, tmp_path / 'unsupported-output')
    assert not (tmp_path / 'unsupported-output').exists()


def test_versioned_api_error_envelope():
    with pytest.raises(InputError) as caught:
        inspect_template('python.bounded-tail-call', '0.9.0')
    assert template_error(caught.value) == {
        'schema_version': '1.0', 'status': 'rejected', 'error': 'InputError',
        'message': 'Unsupported template ID or version; v1 refuses unknown and legacy manifests'}


def test_output_symlink_traversal_is_rejected_before_writes(tmp_path):
    root, request = example('c')
    real = tmp_path / 'real'; real.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable on this host')
    with pytest.raises(InputError, match='symlinks'):
        materialize_template(root, request, link / 'render')
    assert not (real / 'render').exists()
