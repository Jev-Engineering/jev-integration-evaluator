"""Synthetic qualification using the byte-verified, unchanged legacy constructors.

This is not the separately authored corpus or signed/merged release qualification.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import nomination_inventory as bridge
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import digest
from jev_integration_evaluator.scanner import scan_repo
from jev_integration_evaluator.scoring import apply_reviews

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux descriptor backend only')
HOST = '''def a17(x):
    return x.dispatch()

def z93(x):
    return a17(x)
'''


def check_error(code, call, *args, **kwargs):
    with pytest.raises(cap.CapabilityError) as exc:
        call(*args, **kwargs)
    assert exc.value.code == code
    assert str(exc.value) == code


def nomination(report, symbol='z93', pattern='C', file='opaque.py'):
    seam = next(s for s in report['seams']
                if s['source']['qualified_symbol'] == symbol and s['source']['file'] == file)
    anchor = copy.deepcopy(seam['source'])
    return {'schema_version': '1.0', 'discovery_version': cap.VERSION,
            'report_sha256': report['report_sha256'], 'source': anchor, 'seam_id': seam['seam_id'],
            'pattern': pattern, 'proposer': 'offline-synthetic-proposer',
            'rationale': 'Hypothesis about a bounded dispatcher, not permission or measured benefit.',
            'evidence': [{k: anchor[k] for k in ('file', 'file_sha256', 'start_line', 'end_line')}]}


def candidate(prepared, symbol='z93'):
    return next(c for c in prepared['inventory']['candidates'] if c['source']['symbol'] == symbol)


def review(prepared, approved=True):
    c = candidate(prepared)
    return {'schema_version': '1.0', 'prepared_sha256': prepared['prepared_sha256'],
            'reviews': {c['candidate_id']: {'source_sha256': c['source']['source_sha256'],
                         'reviewer': 'offline-synthetic-semantic-reviewer',
                         'reason': 'The fixture is a bounded dispatch hypothesis; missing measurements remain unknown.',
                         'approved': approved}}}


@pytest.fixture
def case(tmp_path):
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'opaque.py').write_text(HOST)
    cfg = load_config()
    report = bridge.discover_repository_capabilities(root, cfg)
    n = nomination(report)
    return root, cfg, report, n


def build(case):
    root, cfg, report, n = case
    return bridge.prepare_nominated_inventory(root, report, [n], cfg)


def test_actual_legacy_scanner_has_no_opaque_candidate_but_bridge_constructs_one(case):
    root, cfg, report, n = case
    before = {p.name: (p.read_bytes(), p.stat().st_mode) for p in root.iterdir()}
    legacy = scan_repo(root, cfg)
    assert not any(c['source']['symbol'] == 'z93' for c in legacy['candidates'])
    prepared = build(case)
    c = candidate(prepared)
    assert c['candidate_id'] == 'JEV-' + digest(['opaque.py', 'z93', 'C'])[:12].upper()
    assert c['source']['source_sha256'] == hashlib.sha256(b'def z93(x):\n    return a17(x)').hexdigest()
    assert c['source']['file_sha256'] == hashlib.sha256(HOST.encode()).hexdigest()
    assert c['semantic_review']['approved'] is False
    assert c['evidence_status'] == 'review_required'
    assert c['pattern'] == 'C'
    assert c['policy']['default_mode'] == 'off'
    assert c['tier'] == 1 and c['deployment_status'] == 'not_validated'
    assert all(v is None for v in c['estimates'].values())
    assert c['evidence'][-1]['nomination_sha256'] == cap._digest(n)
    assert c['evidence'][-1]['anchor'] == n['source']
    assert prepared['inventory_sha256'] == digest(prepared['inventory'])
    assert prepared['prepared_sha256'] == digest({k: v for k, v in prepared.items() if k != 'prepared_sha256'})
    assert prepared['inventory']['scan_fingerprint'] == digest(prepared['inventory']['analysis_identity'])
    assert before == {p.name: (p.read_bytes(), p.stat().st_mode) for p in root.iterdir()}
    assert not (root / '__pycache__').exists()


def test_legacy_review_function_accepts_real_candidate_without_replacement_functions(case):
    prepared = build(case)
    r = review(prepared)
    # Exercise the real pre-existing function as well as the source-bound wrapper.
    old = copy.deepcopy(prepared['inventory'])
    apply_reviews(old, r['reviews'], case[1])
    reviewed = bridge.review_nominated_inventory(case[0], case[2], prepared, r, case[1])
    assert reviewed['inventory'] == old
    assert candidate(reviewed)['semantic_review']['approved'] is True
    assert candidate(reviewed)['estimates'] == candidate(prepared)['estimates']
    assert reviewed['binding_review'] == 'not_performed'
    for key in ('implementation_verified', 'provider_execution_authorized', 'mutation_authorized', 'runtime_activation_authorized'):
        assert reviewed[key] is False
    assert candidate(prepared)['semantic_review']['approved'] is False


def test_negative_semantic_review_is_preserved_not_converted_to_approval(case):
    prepared = build(case)
    r = review(prepared, False)
    reviewed = bridge.review_nominated_inventory(case[0], case[2], prepared, r, case[1])
    c = candidate(reviewed)
    assert c['semantic_review'] == r['reviews'][c['candidate_id']]
    assert c['semantic_review']['approved'] is False


@pytest.mark.parametrize('where', ['wrapper', 'callee', 'other_source', 'config'])
def test_full_snapshot_drift_blocks_semantic_review_even_when_wrapper_slice_is_unchanged(case, where):
    root, cfg, report, n = case
    if where == 'other_source':
        (root / 'other.py').write_text('v=1\n')
    if where == 'config':
        (root / 'pyproject.toml').write_text('[project]\nname="old"\n')
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [nomination(report)], cfg)
    r = review(prepared)
    if where == 'wrapper':
        (root / 'opaque.py').write_text(HOST + '\n# drift\n')
    elif where == 'callee':
        (root / 'opaque.py').write_text(HOST.replace('return x', 'return str(x)'))
    elif where == 'other_source':
        (root / 'other.py').write_text('v=2\n')
    else:
        (root / 'pyproject.toml').write_text('[project]\nname="new"\n')
    check_error('stale_or_tampered_capability_report', bridge.review_nominated_inventory,
                root, report, prepared, r, cfg)


@pytest.mark.parametrize('field', ['inventory', 'admissions', 'prepared_sha256', 'implementation_verified', 'extra'])
def test_preparation_tampering_is_rejected_even_if_hash_is_resealed(case, field):
    prepared = build(case)
    bad = copy.deepcopy(prepared)
    if field == 'inventory':
        candidate(bad)['semantic_review']['approved'] = True
    elif field == 'admissions':
        bad['admissions'][0]['execution_authorized'] = True
    else:
        bad[field] = 'forged'
    if field != 'prepared_sha256':
        bad['prepared_sha256'] = digest({k: v for k, v in bad.items() if k != 'prepared_sha256'})
    assert bad != prepared
    check_error('stale_or_tampered_prepared_inventory', bridge.review_nominated_inventory,
                case[0], case[2], bad, review(bad), case[1])


@pytest.mark.parametrize('field,value', [('estimates', {'quality_gain': 1}), ('dimensions', {}),
                                       ('commands', ['echo', 'unsafe']), ('mutation_authorized', True),
                                       ('binding_review', True), ('source', 'replacement text')])
def test_agent_review_cannot_supply_measurements_commands_or_authority(case, field, value):
    prepared = build(case)
    r = review(prepared)
    next(iter(r['reviews'].values()))[field] = value
    check_error('invalid_repository_review_fields', bridge.review_nominated_inventory,
                case[0], case[2], prepared, r, case[1])


def test_instruction_like_review_reason_is_only_data(case):
    prepared = build(case)
    marker = case[0] / 'MUST_NOT_EXIST'
    r = review(prepared)
    text = f'__import__("pathlib").Path({str(marker)!r}).write_text("not allowed")'
    next(iter(r['reviews'].values()))['reason'] = text
    reviewed = bridge.review_nominated_inventory(case[0], case[2], prepared, r, case[1])
    assert candidate(reviewed)['semantic_review']['reason'] == text
    assert not marker.exists()


def test_matching_old_slice_hash_is_not_sufficient_for_a_new_preparation(case):
    prepared = build(case)
    r = review(prepared)
    r['prepared_sha256'] = '0' * 64
    check_error('source_stale_repository_review', bridge.review_nominated_inventory,
                case[0], case[2], prepared, r, case[1])


@pytest.mark.parametrize('value', ['yes', 1, None, [], {}])
def test_review_approval_must_be_boolean(case, value):
    prepared = build(case)
    r = review(prepared)
    next(iter(r['reviews'].values()))['approved'] = value
    check_error('invalid_repository_review_approval', bridge.review_nominated_inventory,
                case[0], case[2], prepared, r, case[1])


@pytest.mark.parametrize('value', [False, 0, None, 'true'])
def test_review_cannot_waive_hard_real_time(case, value):
    prepared = build(case)
    r = review(prepared)
    next(iter(r['reviews'].values()))['hard_real_time'] = value
    check_error('review_cannot_waive_real_time_exclusion', bridge.review_nominated_inventory,
                case[0], case[2], prepared, r, case[1])


@pytest.mark.parametrize('value', ['none', 'weak', 'equivalent', None, False])
def test_review_cannot_weaken_deterministic_exclusions(case, value):
    prepared = build(case)
    r = review(prepared)
    next(iter(r['reviews'].values()))['deterministic_alternative'] = value
    check_error('review_can_only_strengthen_deterministic_exclusion', bridge.review_nominated_inventory,
                case[0], case[2], prepared, r, case[1])


@pytest.mark.parametrize('field,value', [('hard_real_time', True), ('deterministic_alternative', 'preferred'),
                                       ('deterministic_alternative', 'mandatory')])
def test_semantic_review_can_strengthen_a_mandatory_gate(case, field, value):
    prepared = build(case)
    r = review(prepared)
    next(iter(r['reviews'].values()))[field] = value
    result = bridge.review_nominated_inventory(case[0], case[2], prepared, r, case[1])
    assert candidate(result)['tier'] == 0
    assert candidate(result)['recommendation'] == 'do_not_use'


def test_legacy_gate_cannot_be_bypassed_by_changing_nomination_pattern(tmp_path):
    # Existing source recognizer declares sorted() a deterministic anti-pattern.
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'opaque.py').write_text('def sorted(x):\n    return x\n\ndef z93(x):\n    return sorted(x)\n')
    cfg = load_config()
    report = bridge.discover_repository_capabilities(root, cfg)
    assert next(s for s in report['seams'] if s['source']['qualified_symbol'] == 'z93')['shape'] == 'module-tail-call-v1-preflight'
    check_error('deterministic_operation_shape', bridge.prepare_nominated_inventory,
                root, report, [nomination(report)], cfg)


def test_external_hard_real_time_exclusions_survive_the_bridge(case):
    root, cfg, _, _ = case
    policy = cap.DiscoveryPolicy(max_file_bytes=cfg['repository']['max_file_bytes'],
                                 hard_real_time=('opaque.py::z93',))
    report = bridge.discover_repository_capabilities(root, cfg, policy=policy)
    n = nomination(report)
    check_error('hard_real_time_exclusion', bridge.prepare_nominated_inventory,
                root, report, [n], cfg, policy=policy)
    check_error('stale_or_tampered_capability_report', bridge.prepare_nominated_inventory,
                root, report, [n], cfg)


def test_cfg_exclusions_cannot_be_waived_by_report(case):
    root, cfg, report, n = case
    cfg['repository']['exclude'] = ['opaque.py']
    check_error('stale_or_tampered_capability_report', bridge.prepare_nominated_inventory,
                root, report, [n], cfg)


def test_duplicate_nomination_is_rejected_before_candidates_are_built(case):
    root, cfg, report, n = case
    check_error('duplicate_nominated_placement', bridge.prepare_nominated_inventory,
                root, report, [n, copy.deepcopy(n)], cfg)


def test_multiple_patterns_are_separate_hypotheses_without_duplicate_inventory_ids(case):
    root, cfg, report, n = case
    other = copy.deepcopy(n)
    other['pattern'] = 'A'
    prepared = bridge.prepare_nominated_inventory(root, report, [n, other], cfg)
    assert {c['pattern'] for c in prepared['inventory']['candidates']} == {'A', 'C'}
    assert len({c['candidate_id'] for c in prepared['inventory']['candidates']}) == 2
    assert prepared['inventory']['interactions'][0]['conflict'] is True


def test_ordered_inputs_and_results_do_not_share_mutable_nomination_evidence(case):
    original = copy.deepcopy(case[3])
    prepared = build(case)
    before = copy.deepcopy(prepared)
    case[3]['evidence'].clear()
    case[3]['source']['qualified_symbol'] = 'changed'
    assert prepared == before
    assert prepared['nominations'] == [original]


def test_no_target_command_plugin_import_or_network_is_used_by_bridge(case, monkeypatch):
    import builtins
    import os
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError('unscoped execution attempted')
    real_import = builtins.__import__
    def import_guard(name, *args, **kwargs):
        if name in ('opaque', 'sitecustomize'):
            forbidden()
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', import_guard)
    for owner, name in ((subprocess, 'run'), (subprocess, 'Popen'), (os, 'system'), (socket, 'create_connection')):
        monkeypatch.setattr(owner, name, forbidden)
    prepared = build(case)
    bridge.review_nominated_inventory(case[0], case[2], prepared, review(prepared), case[1])


def test_failed_python_and_other_languages_stay_in_snapshot_and_incomplete(case):
    root, cfg, _, _ = case
    (root / 'broken.py').write_text('def broken(:\n')
    (root / 'other.ts').write_text('export const a = 7;\n')
    (root / 'package.json').write_text('{"scripts":{"test":"MUST_NOT_RUN"}}\n')
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [nomination(report)], cfg)
    inventory = prepared['inventory']
    assert inventory['coverage']['truncated'] is False
    assert inventory['coverage']['analysis_complete_within_policy'] is False
    assert inventory['coverage']['files_analyzed'] == 1
    assert inventory['coverage']['parser_counts'] == {'python_ast': 1, 'unavailable': 1, 'not_requested': 1}
    assert {f['file'] for f in inventory['files']} == {'opaque.py', 'broken.py', 'other.ts'}
    assert inventory['configuration_evidence'][0]['file'] == 'package.json'
    assert candidate(prepared)['semantic_review']['approved'] is False


def test_change_during_fact_read_is_rejected(case, monkeypatch):
    old_facts = bridge._facts
    old_read = cap._read_at
    def changed(parent, path, maximum):
        raw, mode = old_read(parent, path, maximum)
        return raw + b'\n# changed bytes\n', mode
    def during_facts(*args, **kwargs):
        with monkeypatch.context() as m:
            m.setattr(cap, '_read_at', changed)
            return old_facts(*args, **kwargs)
    monkeypatch.setattr(bridge, '_facts', during_facts)
    check_error('source_changed_during_inventory_preparation', build, case)


def test_global_architecture_limits_are_checked_before_graph_construction(case, monkeypatch):
    monkeypatch.setattr(bridge, 'MAX_INVENTORY_SYMBOLS', 1)
    def forbidden(*args, **kwargs):
        raise AssertionError('unbounded graph construction')
    monkeypatch.setattr(bridge, 'build_architecture', forbidden)
    check_error('inventory_architecture_bound', build, case)


def test_new_defaults_record_evaluator_limits_without_relaxing_them(case):
    root, cfg, report, n = case
    assert report['policy']['max_file_bytes'] == cfg['repository']['max_file_bytes']
    cfg['depth'] = 'QUICK'
    new = bridge.discover_repository_capabilities(root, cfg)
    assert new['policy']['max_files'] == 500
    bridge.prepare_nominated_inventory(root, new, [nomination(new)], cfg)
    check_error('capability_bounds_exceed_evaluator_configuration', bridge.discover_repository_capabilities,
                root, cfg, policy=cap.DiscoveryPolicy(max_files=1000, max_file_bytes=1_000_000))


@pytest.mark.parametrize('edit', ['extra', 'missing', 'nested', 'negative', 'wrong_type'])
def test_invalid_configuration_is_redacted_and_rejected(case, edit):
    cfg = copy.deepcopy(case[1])
    if edit == 'extra':
        cfg['execution_authorized'] = True
    elif edit == 'missing':
        del cfg['repository']
    elif edit == 'nested':
        cfg['runtime']['approval'] = True
    elif edit == 'negative':
        cfg['runtime']['max_cost_per_task'] = -1
    else:
        cfg['repository']['max_files'] = True
    check_error('invalid_evaluator_configuration', bridge.discover_repository_capabilities, case[0], cfg)


def test_empty_repository_retains_no_candidate_not_no_useful_claim(tmp_path):
    root = tmp_path / 'empty'; root.mkdir()
    cfg = load_config()
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [], cfg)
    assert prepared['inventory']['candidates'] == []
    assert report['discovery_outcome'] == 'no_candidates_discovered'
    assert prepared['semantic_review'] == 'required'


def test_pure_deterministic_candidate_cannot_receive_approval(tmp_path):
    root = tmp_path / 'pure'; root.mkdir()
    (root / 'opaque.py').write_text('def z93(x):\n    return x + 1\n')
    cfg = load_config()
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [], cfg)
    assert candidate(prepared)['tier'] == 0
    check_error('legacy_deterministic_or_real_time_exclusion', bridge.review_nominated_inventory,
                root, report, prepared, review(prepared), cfg)


def test_source_fact_test_presence_is_preserved_as_a_proxy_not_runtime_coverage(case):
    root, cfg, _, _ = case
    (root / 'tests').mkdir()
    (root / 'tests/test_never_run.py').write_text('raise RuntimeError("not authorized to execute")\n')
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [nomination(report)], cfg)
    d = candidate(prepared)['dimensions']['testability']
    assert d['value'] == 0.8
    assert 'not candidate test coverage' in d['rationale']
    assert 'runtime_evidence' not in candidate(prepared)
    assert all(v is None for v in candidate(prepared)['estimates'].values())


def test_generated_candidate_and_reviewed_inventory_pass_unchanged_main_schema(case):
    from jev_integration_evaluator.contracts import validate_contract
    prepared = build(case)
    validate_contract(prepared['inventory'], 'inventory')
    reviewed = bridge.review_nominated_inventory(case[0], case[2], prepared, review(prepared), case[1])
    validate_contract(reviewed['inventory'], 'inventory')


@pytest.mark.parametrize('name', ['repository-nominated-inventory-v1', 'repository-semantic-review-v1', 'repository-reviewed-inventory-v1'])
def test_bridge_schema_mirrors_are_identical_and_valid(name):
    import json
    import jsonschema
    root = Path(__file__).resolve().parents[1]
    left = root / 'schemas' / (name + '.schema.json')
    right = root / 'jev_integration_evaluator/data' / (name + '.schema.json')
    assert left.read_bytes() == right.read_bytes()
    jsonschema.Draft202012Validator.check_schema(json.loads(left.read_text()))


def test_all_real_bridge_outputs_and_review_input_validate(case):
    from jev_integration_evaluator.contracts import validate_contract
    prepared = build(case)
    r = review(prepared)
    result = bridge.review_nominated_inventory(case[0], case[2], prepared, r, case[1])
    for value, name in [(prepared, bridge.CONTRACT), (r, 'repository-semantic-review-v1'),
                        (result, 'repository-reviewed-inventory-v1')]:
        validate_contract(value, name)


@pytest.mark.parametrize('field', ['implementation_verified', 'mutation_authorized', 'provider_execution_authorized', 'runtime_activation_authorized'])
def test_bridge_output_schemas_forbid_adding_authority(case, field):
    from jev_integration_evaluator.contracts import validate_contract
    from jev_integration_evaluator.io import InputError
    prepared = build(case)
    result = bridge.review_nominated_inventory(case[0], case[2], prepared, review(prepared), case[1])
    for value in (prepared, result):
        value[field] = True
        with pytest.raises(InputError):
            validate_contract(value, value['contract'])


def test_bridge_schema_preserves_strict_legacy_candidate_properties(case):
    from jev_integration_evaluator.contracts import validate_contract
    from jev_integration_evaluator.io import InputError
    p = build(case)
    candidate(p)['override_authority'] = True
    with pytest.raises(InputError):
        validate_contract(p, p['contract'])


def test_external_hard_real_time_gate_applies_to_unnominated_heuristic_candidate(tmp_path):
    root = tmp_path / 'host'
    root.mkdir()
    source = 'def choose_route(x):\n    return x.dispatch()\n'
    (root / 'opaque.py').write_text(source)
    cfg = load_config()
    policy = cap.DiscoveryPolicy(max_file_bytes=cfg['repository']['max_file_bytes'],
                                 hard_real_time=('opaque.py::choose_route',))
    report = bridge.discover_repository_capabilities(root, cfg, policy=policy)
    prepared = bridge.prepare_nominated_inventory(root, report, [], cfg, policy=policy)
    c = candidate(prepared, 'choose_route')
    assert c['tier'] == 0
    assert c['hard_real_time'] is True
    r = {'schema_version': '1.0', 'prepared_sha256': prepared['prepared_sha256'],
         'reviews': {c['candidate_id']: {'source_sha256': c['source']['source_sha256'],
                     'reviewer': 'synthetic-reviewer', 'reason': 'Cannot waive caller policy.',
                     'approved': True}}}
    check_error('legacy_deterministic_or_real_time_exclusion', bridge.review_nominated_inventory,
                root, report, prepared, r, cfg, policy=policy)


def test_closed_identity_wrapper_is_ineligible_even_with_opaque_names(case):
    root, cfg, _, _ = case
    (root / 'opaque.py').write_text(HOST.replace('return x.dispatch()', 'return x'))
    report = bridge.discover_repository_capabilities(root, cfg)
    check_error('deterministic_operation_shape', bridge.prepare_nominated_inventory,
                root, report, [nomination(report)], cfg)


def test_closed_deterministic_heuristic_candidate_cannot_receive_semantic_approval(tmp_path):
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'opaque.py').write_text('def a17(x):\n    return x\n\ndef choose_route(x):\n    return a17(x)\n')
    cfg = load_config()
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [], cfg)
    c = candidate(prepared, 'choose_route')
    assert c['tier'] == 0 and c['deterministic_alternative'] == 'mandatory'
    assert c['evidence'][-1]['reasons'] == ['deterministic_operation_shape']
    r = {'schema_version': '1.0', 'prepared_sha256': prepared['prepared_sha256'],
         'reviews': {c['candidate_id']: {'source_sha256': c['source']['source_sha256'],
                     'reviewer': 'synthetic-reviewer', 'reason': 'Cannot replace identity with a model.',
                     'approved': True}}}
    check_error('legacy_deterministic_or_real_time_exclusion', bridge.review_nominated_inventory,
                root, report, prepared, r, cfg)


@pytest.mark.parametrize('kind', ['ambiguous', 'symbol_budget'])
def test_legacy_facts_cannot_create_candidates_outside_admitted_capability_seams(tmp_path, kind):
    root = tmp_path / 'host'
    root.mkdir()
    source = 'def choose_route(x):\n    return x.dispatch()\n'
    source += (source if kind == 'ambiguous' else 'def a17(x):\n    return x.dispatch()\n')
    (root / 'opaque.py').write_text(source)
    cfg = load_config()
    policy = cap.DiscoveryPolicy(max_file_bytes=cfg['repository']['max_file_bytes'],
                                 max_symbols=1 if kind == 'symbol_budget' else 2000)
    report = bridge.discover_repository_capabilities(root, cfg, policy=policy)
    prepared = bridge.prepare_nominated_inventory(root, report, [], cfg, policy=policy)
    assert prepared['inventory']['candidates'] == []
    assert prepared['inventory']['coverage']['nomination_bridge']['withheld_candidates']
    if kind == 'symbol_budget':
        assert prepared['inventory']['coverage']['analysis_complete_within_policy'] is False
        assert prepared['inventory']['coverage']['truncated'] is True


def test_published_discovery_and_admission_contracts_are_used_unchanged(case):
    root, cfg, report, n = case
    policy = cap.DiscoveryPolicy.from_json(report['policy'])
    assert report == cap.discover_repository(root, policy)
    prepared = build(case)
    assert prepared['admissions'] == [cap.admit_nomination(
        root, n, expected_report_sha256=report['report_sha256'], policy=policy)]
    assert prepared['bridge_engine_sha256'] == bridge._engine_identity()
    assert prepared['inventory']['coverage']['nomination_bridge']['bridge_engine_sha256'] == prepared['bridge_engine_sha256']


def test_bridge_engine_drift_blocks_existing_review_even_when_source_is_identical(case, monkeypatch):
    prepared = build(case)
    monkeypatch.setattr(bridge, '_engine_identity', lambda: '0' * 64)
    check_error('stale_or_tampered_prepared_inventory', bridge.review_nominated_inventory,
                case[0], case[2], prepared, review(prepared), case[1])


def test_bridge_engine_change_during_preparation_is_rejected(case, monkeypatch):
    identities = iter(['0' * 64, '1' * 64])
    monkeypatch.setattr(bridge, '_engine_identity', lambda: next(identities))
    check_error('bridge_engine_changed_during_preparation', build, case)


@pytest.mark.parametrize('where', ['before_review', 'during_facts'])
def test_file_mode_changes_cannot_reuse_a_preparation(case, monkeypatch, where):
    root, cfg, report, _ = case
    prepared = build(case)
    if where == 'before_review':
        path = root / 'opaque.py'
        path.chmod(path.stat().st_mode ^ 0o100)
        check_error('stale_or_tampered_capability_report', bridge.review_nominated_inventory,
                    root, report, prepared, review(prepared), cfg)
    else:
        old_facts, old_read = bridge._facts, cap._read_at
        def changed(parent, path, maximum):
            raw, mode = old_read(parent, path, maximum)
            return raw, mode ^ 0o100
        def during_facts(*args, **kwargs):
            with monkeypatch.context() as m:
                m.setattr(cap, '_read_at', changed)
                return old_facts(*args, **kwargs)
        monkeypatch.setattr(bridge, '_facts', during_facts)
        check_error('source_changed_during_inventory_preparation', build, case)


def test_review_is_bound_to_full_caller_configuration_and_policy(case):
    prepared = build(case)
    cfg = copy.deepcopy(case[1])
    cfg['thresholds']['strong_candidate'] = 0.6
    check_error('stale_or_tampered_prepared_inventory', bridge.review_nominated_inventory,
                case[0], case[2], prepared, review(prepared), cfg)
    policy = replace(cap.DiscoveryPolicy.from_json(case[2]['policy']), max_entries=19999)
    check_error('stale_or_tampered_capability_report', bridge.review_nominated_inventory,
                case[0], case[2], prepared, review(prepared), case[1], policy=policy)


def test_active_runtime_configuration_cannot_activate_discovery_or_semantic_review(case):
    root, cfg, _, _ = case
    cfg['runtime']['mode'] = 'active'
    cfg['mode'] = 'implementation'
    report = bridge.discover_repository_capabilities(root, cfg)
    prepared = bridge.prepare_nominated_inventory(root, report, [nomination(report)], cfg)
    reviewed = bridge.review_nominated_inventory(root, report, prepared, review(prepared), cfg)
    for result in (prepared, reviewed):
        assert all(c['policy']['default_mode'] == 'off' for c in result['inventory']['candidates'])
        assert result['binding_review'] == 'not_performed'
        assert all(result[field] is False for field in (
            'implementation_verified', 'provider_execution_authorized',
            'mutation_authorized', 'runtime_activation_authorized'))
