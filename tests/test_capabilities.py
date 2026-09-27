"""Synthetic discovery assertions. Not the independent #9 qualification corpus."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from jev_integration_evaluator import capabilities as c

HOST = '''# Opaque names, independently callable baseline; never executed by discovery.
import sys

def n4(p):
    return p.dispatch()

def v8(p):
    """A source-anchored hypothesis, not permission or a measured benefit."""
    return n4(p)

R2 = {"choice-a": n4}
'''


@pytest.fixture
def host(tmp_path):
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'opaque.py').write_text(HOST, encoding='utf-8')
    return root


def proposal(report, symbol='v8'):
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol'] == symbol)
    src = deepcopy(seam['source'])
    return {'schema_version':'1.0','discovery_version':c.VERSION,
            'report_sha256':report['report_sha256'],'seam_id':seam['seam_id'],
            'source':src, 'pattern':'C', 'proposer':'synthetic-test-proposer',
            'rationale':'Review finite dispatch options; runtime intent remains unverified.',
            'evidence':[{k:src[k] for k in ('file','file_sha256','start_line','end_line')}]}


def admit(root, report, value=None, **kwargs):
    return c.admit_nomination(root, value or proposal(report),
                             expected_report_sha256=report['report_sha256'], **kwargs)


def expect(code, function, *args, **kwargs):
    with pytest.raises(c.CapabilityError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


def test_opaque_nomination_is_source_bound_and_non_authoritative(host):
    before = (host/'opaque.py').read_bytes()
    report = c.discover_repository(host)
    assert report['discovery_outcome'] == 'review_required'
    assert report['coverage']['complete_within_policy']
    assert report['registry_possibilities'][0]['entry_count'] == 1
    candidate = admit(host, report)
    assert candidate['status'] == 'nominated_pending_semantic_and_binding_review'
    assert candidate['semantic_review'] == 'not_performed'
    assert candidate['benefit'] is None and not candidate['execution_qualified']
    assert not any(candidate['authorization'].values())
    assert (host/'opaque.py').read_bytes() == before
    assert candidate['source']['file_sha256'] == hashlib.sha256(before).hexdigest()
    assert admit(host, report) == candidate


def test_report_is_repeatable_and_not_relocatable(host, tmp_path):
    report = c.discover_repository(host)
    assert report == c.discover_repository(host)
    other = tmp_path/'other'; other.mkdir()
    (other/'opaque.py').write_text(HOST)
    expect('stale_report_or_policy', admit, other, report)


@pytest.mark.parametrize('change', ['append','new_source','configuration','mode','delete'])
def test_drift_invalidates_old_report(host, change):
    report = c.discover_repository(host)
    if change == 'append':
        with (host/'opaque.py').open('a') as f: f.write('\n# changed source\n')
    elif change == 'new_source': (host/'added.py').write_text('x = 1\n')
    elif change == 'configuration': (host/'pyproject.toml').write_text('[project]\nname="host"\n')
    elif change == 'mode': (host/'opaque.py').chmod(0o600)
    else: (host/'opaque.py').unlink()
    expect('stale_report_or_policy', admit, host, report)


@pytest.mark.parametrize('field,value', [('file','../outside.py'),('qualified_symbol','missing'),
    ('start_line',1),('end_line',999),('file_sha256','0'*64),('ast_sha256','0'*64)])
def test_forged_source_anchor_rejected(host, field, value):
    report = c.discover_repository(host); p = proposal(report)
    p['source'][field] = value
    expect('source_anchor_mismatch', admit, host, report, p)


def test_unknown_seam_rejected(host):
    report=c.discover_repository(host); p=proposal(report); p['seam_id']='0'*64
    expect('unknown_or_ambiguous_seam',admit,host,report,p)


@pytest.mark.parametrize('field,value', [('approved',True),('command','touch not-authorized'),
    ('estimates',{'quality_gain':0.9}),('authorization',{'execution':True}),
    ('runtime_mode','active'),('replacement_source','print("unapproved")')])
def test_agent_cannot_add_scope_measurements_or_replacement_source(host, field, value):
    r=c.discover_repository(host); p=proposal(r); p[field]=value
    expect('invalid_candidate_nomination',admit,host,r,p)


def test_agent_text_is_data(host, tmp_path):
    r=c.discover_repository(host); p=proposal(r)
    marker=tmp_path/'NEVER'
    p['rationale']=f'__import__("pathlib").Path({str(marker)!r}).touch()'
    a=admit(host,r,p)
    assert a['rationale']==p['rationale'] and not marker.exists()
    assert not any(a['authorization'].values())


@pytest.mark.parametrize('code', ['return 2 + 3','return p == 4','return p',
                                  'return abs(p)'])
def test_deterministic_candidates_cannot_be_nominated(host, code):
    (host/'opaque.py').write_text('def n4(p):\n    '+code+'\n\ndef v8(p):\n    return n4(p)\n')
    r=c.discover_repository(host)
    expect('deterministic_operation_shape',admit,host,r)


def test_hard_real_time_and_policy_cannot_be_overridden(host):
    policy=c.DiscoveryPolicy(hard_real_time=('opaque.py::v8',))
    r=c.discover_repository(host,policy)
    expect('hard_real_time_exclusion',admit,host,r,policy=policy)
    expect('stale_report_or_policy',admit,host,r)
    other=replace(policy,exclude=('other.py',))
    expect('stale_report_or_policy',admit,host,r,policy=other)


@pytest.mark.parametrize('body', [
    'def v8(p):\n    return n4(p)\n',
    'v8 = n4\n',
    'def helper(x=(v8 := n4)):\n    return x\n',
    'def helper(*x: (v8 := n4)):\n    return x\n',
    'try:\n    pass\nexcept Exception as v8:\n    pass\n',
    'match 1:\n    case v8:\n        pass\n',
])
def test_module_rebinding_is_ambiguous(host, body):
    with (host/'opaque.py').open('a') as f:f.write('\n'+body)
    r=c.discover_repository(host)
    expect('ambiguous_symbol',admit,host,r)


@pytest.mark.parametrize('file,expected', [
    ('src/pkg/host.py','src_layout_sighting'),
    ('pkg/host.py','namespace_or_directory_unresolved'),
])
def test_package_layout_is_not_legacy_recipe_qualification(tmp_path,file,expected):
    root=tmp_path/'repo'; target=root/file;target.parent.mkdir(parents=True)
    target.write_text(HOST)
    r=c.discover_repository(root)
    assert expected in r['layouts']
    assert all(s['shape']=='unsupported_or_unresolved' for s in r['seams'])
    assert not any(s['execution_qualified'] for s in r['seams'])
    assert admit(root,r)['shape']=='unsupported_or_unresolved'


def test_regular_package_and_configuration_sightings(tmp_path):
    root=tmp_path/'repo'; (root/'pkg').mkdir(parents=True)
    (root/'pkg/__init__.py').write_text('')
    (root/'pkg/host.py').write_text(HOST)
    (root/'pyproject.toml').write_text('[build-system]\nrequires=["UNAPPROVED"]\n')
    r=c.discover_repository(root)
    assert 'regular_package_sighting' in r['layouts']
    assert next(f for f in r['files'] if f['file']=='pyproject.toml')['configuration_sighting']


@pytest.mark.parametrize('content', ['export function a(x) {return b(x)}', 'not valid syntax'])
def test_ts_is_honestly_unparsed_without_target_tools(tmp_path,content):
    (tmp_path/'host.ts').write_text(content)
    (tmp_path/'package.json').write_text('{"scripts":{"install":"DO NOT RUN"}}')
    r=c.discover_repository(tmp_path)
    assert not r['seams'] and r['discovery_outcome']=='incomplete_analysis'
    assert not r['coverage']['complete_within_policy']
    assert next(f for f in r['files'] if f['file']=='host.ts')['parser']=='not_requested'


def test_mixed_language_keeps_opaque_nomination_and_incomplete_analysis(host):
    (host/'other.rs').write_text('fn main() {}')
    r=c.discover_repository(host)
    assert r['discovery_outcome']=='incomplete_analysis'
    assert not admit(host,r)['analysis_complete_within_policy']


def test_empty_does_not_claim_no_useful_placement(tmp_path):
    r=c.discover_repository(tmp_path)
    assert r['discovery_outcome']=='no_candidates_discovered'
    assert 'no_useful_placement' not in json.dumps(r)


@pytest.mark.parametrize('raw', [b'\xff',b'# coding: latin-1\nx=1\n',
    b'\xef\xbb\xbfdef a(x):\n return x\n',b'bad syntax (', b'x=1\rx=2\r'])
def test_encoding_and_parser_failures_are_incomplete(host,raw):
    (host/'bad.py').write_bytes(raw)
    r=c.discover_repository(host)
    assert not r['coverage']['complete_within_policy']
    assert r['discovery_outcome']=='incomplete_analysis'


@pytest.mark.parametrize('policy,reason', [
    (c.DiscoveryPolicy(max_files=1),'file_count_budget'),
    (c.DiscoveryPolicy(max_file_bytes=5),'file_byte_budget'),
    (c.DiscoveryPolicy(max_symbols=1),'symbol_budget'),
    (c.DiscoveryPolicy(max_ast_nodes=2),'ast_node_budget'),
    (c.DiscoveryPolicy(max_entries=1),'entry_budget'),
])
def test_limits_are_not_exhaustive_negative_results(host,policy,reason):
    (host/'second.py').write_text(HOST)
    r=c.discover_repository(host,policy)
    assert not r['coverage']['complete_within_policy']
    assert reason in [n['reason'] for n in r['coverage']['limitations']]


def test_report_byte_limit_fails_closed(host):
    expect('report_byte_budget',c.discover_repository,host,c.DiscoveryPolicy(max_report_bytes=1))


@pytest.mark.parametrize('policy', [{'max_files':True},{'max_entries':0},{'exclude':['../outside']},
    {'hard_real_time':'*'},{'max_file_bytes':float('inf')},{'activate':True}])
def test_policy_rejects_unsafe_or_unknown_values(policy):
    expect('invalid_discovery_policy',c.DiscoveryPolicy.from_json,policy)


def test_source_is_never_imported_and_config_hooks_never_run(host,tmp_path,monkeypatch):
    marker=tmp_path/'sentinel'
    with (host/'opaque.py').open('a') as f:
        f.write(f'\n__import__("pathlib").Path({str(marker)!r}).touch()\nraise RuntimeError("NEVER")\n')
    (host/'conftest.py').write_text('raise RuntimeError("do not execute")')
    (host/'setup.py').write_text('raise RuntimeError("do not install")')
    def fail(*a,**kw): raise AssertionError('unexpected subprocess')
    monkeypatch.setattr(subprocess,'run',fail)
    monkeypatch.setattr(subprocess,'Popen',fail)
    c.discover_repository(host)
    assert not marker.exists()


def test_symlink_and_sensitive_exclusions(host,tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    (outside/'private.py').write_text('DO NOT READ THIS')
    (host/'leak.py').symlink_to(outside/'private.py')
    (host/'linked_dir').symlink_to(outside,target_is_directory=True)
    (host/'.env').write_text('DO NOT READ THIS')
    (host/'secrets').mkdir();(host/'secrets/h.py').write_text(HOST)
    (host/'node_modules').mkdir();(host/'node_modules/h.py').write_text(HOST)
    r=c.discover_repository(host)
    assert {f['file'] for f in r['files']}=={'opaque.py'}
    assert 'DO NOT READ THIS' not in json.dumps(r)
    assert 'secrets/h.py' not in json.dumps(r)


def test_hardlinks_are_not_external_source_access(host,tmp_path):
    outside=tmp_path/'outside.py';outside.write_text(HOST)
    os.link(outside,host/'linked.py')
    r=c.discover_repository(host)
    assert 'linked.py' not in {f['file'] for f in r['files']}
    assert 'hardlink_excluded' in [n['reason'] for n in r['coverage']['limitations']]


def test_fifo_never_blocks_or_becomes_source(host):
    os.mkfifo(host/'pipe.py')
    r=c.discover_repository(host)
    assert 'non_regular_file' in [n['reason'] for n in r['coverage']['limitations']]


def test_nomination_evidence_requires_current_in_root_hash_and_lines(host):
    r=c.discover_repository(host)
    for field,value,code in [('file','../outside.py','missing_seam_evidence'),
        ('file_sha256','0'*64,'evidence_anchor_mismatch'),
        ('end_line',999,'evidence_anchor_mismatch')]:
        p=proposal(r);p['evidence'][0][field]=value
        expect(code,admit,host,r,p)


def test_unqualified_methods_and_async_remain_unqualified(host):
    (host/'b.py').write_text('class C:\n def f(self,x):\n  return x.run()\n\nasync def a(x):\n return await x.run()\n')
    r=c.discover_repository(host)
    assert all(s['shape']=='unsupported_or_unresolved' for s in r['seams'] if s['source']['file']=='b.py')


def test_async_baseline_does_not_get_synchronous_preflight(host):
    (host/'opaque.py').write_text('async def n4(p):\n return await p.run()\n\ndef v8(p):\n return n4(p)\n')
    r=c.discover_repository(host)
    assert next(s for s in r['seams'] if s['source']['qualified_symbol']=='v8')['shape']=='unsupported_or_unresolved'


def test_mirrored_schemas_are_strict_and_identical():
    root=Path(__file__).resolve().parents[1]
    for name in ('repository-capabilities','candidate-nomination','admitted-nomination'):
        a=root/'schemas'/f'{name}.schema.json'; b=root/'jev_integration_evaluator/data'/a.name
        assert a.read_bytes()==b.read_bytes()
        schema=json.loads(a.read_text());jsonschema.Draft202012Validator.check_schema(schema)
        def walk(node):
            if isinstance(node,dict):
                if node.get('type')=='object': assert node['additionalProperties'] is False
                for value in node.values(): walk(value)
            elif isinstance(node,list):
                for value in node:walk(value)
        walk(schema)


def test_cli_private_exclusive_output_and_no_target_write(host,tmp_path,capsys):
    out=tmp_path/'report.json'
    assert c.main(['discover','--repo',str(host),'--out',str(out)])==0
    first=out.read_bytes();assert os.stat(out).st_mode&0o777==0o600
    assert c.main(['discover','--repo',str(host),'--out',str(out)])==2
    assert out.read_bytes()==first
    assert c.main(['discover','--repo',str(host),'--out',str(host/'report.json')])==2
    assert not (host/'report.json').exists()
    captured=capsys.readouterr()
    assert str(host) not in captured.out+captured.err


def test_cli_rejects_repository_policy(host,tmp_path):
    (host/'policy.json').write_text('{}')
    assert c.main(['discover','--repo',str(host),'--policy',str(host/'policy.json'),
                   '--out',str(tmp_path/'report.json')])==2


@pytest.mark.parametrize('text', ['{"a":1,"a":2}','{"a":NaN}','['*2000])
def test_input_json_rejects_ambiguity_and_nonfinite(tmp_path,text):
    p=tmp_path/'input';p.write_text(text)
    with pytest.raises(c.CapabilityError):c._load(p)


def test_detects_source_change_between_passes(host,monkeypatch):
    original=c._walk; calls=0
    def changing(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2:
            with (host/'opaque.py').open('a') as f:f.write('\n# changed\n')
        yield from original(*args,**kwargs)
    monkeypatch.setattr(c,'_walk',changing)
    expect('source_changed_during_discovery',c.discover_repository,host)


def test_descriptor_read_rejects_raced_symlink(host,tmp_path,monkeypatch):
    original=c._read_at; changed=False
    outside=tmp_path/'outside.py';outside.write_text('NEVER READ EXTERNAL SOURCE')
    def race(parent,name,limit):
        nonlocal changed
        if not changed and name=='opaque.py':
            changed=True;(host/name).unlink();(host/name).symlink_to(outside)
        return original(parent,name,limit)
    monkeypatch.setattr(c,'_read_at',race)
    r=c.discover_repository(host)
    assert not r['files']
    assert not r['coverage']['complete_within_policy']


def test_registry_rejects_duplicates_dynamic_and_shadowed_names(host):
    with (host/'opaque.py').open('a') as f:
        f.write('R2 = {"other": n4}\nD = {"a": n4, "a": n4}\nX = {**R2}\n')
    r=c.discover_repository(host)
    assert r['registry_possibilities']==[]
