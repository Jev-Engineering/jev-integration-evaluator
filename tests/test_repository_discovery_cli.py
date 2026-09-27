"""End-to-end command tests on disposable assistant-authored synthetic hosts."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import cli
from jev_integration_evaluator.repository_discovery import main

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux descriptor backend only')
ROOT = Path(__file__).resolve().parents[1]


def invoke(host, *args):
    output = Path(tempfile.mkdtemp(prefix='private-discovery-',dir=host.parent))/'artifact.json'
    bootstrap = 'import sys;sys.path.insert(0,'+repr(str(ROOT))+');from jev_integration_evaluator.cli import main;raise SystemExit(main(sys.argv[1:]))'
    result = subprocess.run([sys.executable, '-I', '-c', bootstrap, 'repository-discovery',
                             str(host), '--out', str(output), *args], cwd=host, capture_output=True, text=True, timeout=20)
    assert not result.stderr, result.stderr
    summary = json.loads(result.stdout)
    if result.returncode:
        assert not output.exists()
        return result.returncode, summary
    value=json.loads(output.read_text(encoding='utf-8'))
    assert summary=={'status':'written','artifact_sha256':cap._digest(value)}
    assert output.stat().st_mode & 0o777 == 0o600
    return result.returncode, value


def save(path, value):
    path.write_text(json.dumps(value))
    return str(path)


@pytest.fixture
def fixture(tmp_path):
    host = tmp_path/'host'
    host.mkdir()
    (host/'opaque.py').write_text('def q5(x):\n    return x.dispatch()\n\ndef z93(x):\n    return q5(x)\n')
    return host, tmp_path


def prepare(fixture):
    host, outside = fixture
    code, report = invoke(host)
    assert code == 0
    seam = next(s for s in report['seams'] if s['source']['qualified_symbol']=='z93')
    anchor=seam['source']
    nomination = {'schema_version':'1.0','discovery_version':cap.VERSION,
                  'report_sha256':report['report_sha256'],'seam_id':seam['seam_id'],'source':anchor,
                  'pattern':'C', 'proposer':'synthetic-command-test', 'rationale':'Only a routing hypothesis.',
                  'evidence':[{k:anchor[k] for k in ('file','file_sha256','start_line','end_line')}]}
    reportfile = save(outside/'capabilities.json', report)
    nominationsfile = save(outside/'nominations.json', [nomination])
    code, prepared = invoke(host, '--stage', 'prepare', '--capabilities', reportfile, '--nominations', nominationsfile)
    assert code == 0
    return prepared, reportfile


def test_three_stage_cli_uses_existing_inventory_and_reviews_without_target_execution(fixture,capsys):
    host, outside = fixture
    (host/'sitecustomize.py').write_text('raise AssertionError("TARGET CODE MUST NOT EXECUTE")\n')
    before = {p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}
    prepared, reportfile = prepare(fixture)
    c = next(c for c in prepared['inventory']['candidates'] if c['source']['symbol']=='z93')
    assert c['semantic_review']['approved'] is False
    reviewed_input = {'schema_version':'1.0','prepared_sha256':prepared['prepared_sha256'],
                      'reviews':{c['candidate_id']:{'source_sha256':c['source']['source_sha256'],
                                'reviewer':'synthetic-test-opinion-not-permission','reason':'Reviewed fixture hypothesis.',
                                'approved':True}}}
    preparedfile = save(outside/'prepared.json', prepared)
    reviewfile = save(outside/'review.json', reviewed_input)
    code, reviewed = invoke(host, '--stage', 'review', '--capabilities', reportfile,
                           '--prepared', preparedfile, '--review', reviewfile)
    assert code == 0
    candidate = next(c for c in reviewed['inventory']['candidates'] if c['source']['symbol']=='z93')
    assert candidate['semantic_review']['approved'] is True
    assert all(v is None for v in candidate['estimates'].values())
    assert candidate['policy']['default_mode'] == 'off'
    assert reviewed['binding_review'] == 'not_performed'
    for k in ('implementation_verified','mutation_authorized','provider_execution_authorized','runtime_activation_authorized'):
        assert reviewed[k] is False
    from jev_integration_evaluator.contracts import validate_contract
    for row in reviewed['inventory']['candidates']:
        validate_contract(row,'opportunity')
    for kind,value in [('repository-nominated-inventory-v1',prepared),
                       ('repository-semantic-review-v1',reviewed_input),
                       ('repository-reviewed-inventory-v1',reviewed)]:
        path=save(outside/(kind+'.json'),value)
        assert cli.main(['validate','--kind',kind,'--input',path])==0
        assert json.loads(capsys.readouterr().out)=={'status':'valid','kind':kind,'records':1,'source_revalidated':False}
        altered={**value,'private_override':'PRIVATE_REVIEW_SENTINEL'}
        save(Path(path),altered)
        assert cli.main(['validate','--kind',kind,'--input',path])==2
        message=capsys.readouterr()
        assert 'PRIVATE_REVIEW_SENTINEL' not in message.out+message.err
        assert str(outside) not in message.out+message.err
    assert before == {p.name:(p.read_bytes(),p.stat().st_mode) for p in host.iterdir()}


@pytest.mark.parametrize('args', [('--stage','prepare'), ('--stage','review'), ('--review','missing'),
                                  ('--stage','prepare','--capabilities','missing'),
                                  ('--stage','review','--nominations','missing')])
def test_stage_fields_are_not_implicitly_inferred_or_executed(fixture, args):
    code, data = invoke(fixture[0], *args)
    assert code == 2 and data == {'status':'blocked','reason':'stage_input_mismatch'}


@pytest.mark.parametrize('data', ['{"mode": "implementation", "command":"echo secret"}',
                                 '{"x":1,"x":2}', '{"x":NaN}', 'not-json', '[]'])
def test_invalid_config_returns_only_redacted_code(fixture, data):
    host, outside = fixture
    config = outside/'config.json'
    config.write_text(data)
    code, value = invoke(host, '--config', str(config))
    assert code == 2 and value['status']=='blocked'
    assert set(value)=={'status','reason'} and 'secret' not in json.dumps(value)


def test_direct_cli_entrypoint_catches_external_file_failures(fixture, capsys):
    assert main([str(fixture[0]), '--out',str(fixture[1]/'out.json'), '--policy','/not-present/policy.json'])==2
    assert json.loads(capsys.readouterr().out)=={'status':'blocked','reason':'input_unavailable_or_invalid'}


def test_repository_discovery_requires_private_output(fixture,capsys):
    with pytest.raises(SystemExit) as caught:
        main([str(fixture[0])])
    assert caught.value.code==2
    assert json.loads(capsys.readouterr().out)=={'status':'blocked','reason':'invalid_command_arguments'}


def test_central_command_preserves_external_private_output(fixture,capsys):
    host,outside=fixture
    out=outside/'private-report.json'
    args=['repository-discovery',str(host),'--out',str(out)]
    assert cli.main(args)==0
    content=out.read_bytes()
    assert str(host) not in capsys.readouterr().out
    assert out.stat().st_mode & 0o777==0o600
    assert cli.main(args)==2
    assert out.read_bytes()==content
    assert json.loads(capsys.readouterr().out)['reason']=='output_unavailable_or_exists'
    assert cli.main(['repository-discovery',str(host),'--out',str(host/'forbidden.json')])==2
    assert not (host/'forbidden.json').exists()
    assert json.loads(capsys.readouterr().out)['reason']=='output_must_be_outside_repository'


@pytest.mark.parametrize('option',['--config','--policy'])
def test_target_cannot_supply_caller_configuration(fixture,capsys,option):
    host,outside=fixture
    internal=host/'untrusted.json';internal.write_text('{}')
    assert cli.main(['repository-discovery',str(host),option,str(internal),'--out',str(outside/'out.json')])==2
    assert not (outside/'out.json').exists()
    assert json.loads(capsys.readouterr().out)['reason']=='configuration_must_be_external'


def test_external_configuration_and_policy_are_applied(fixture):
    from jev_integration_evaluator.config import DEFAULT
    host,outside=fixture
    policy=save(outside/'policy.json',{'hard_real_time':['opaque.py::z93']})
    code,report=invoke(host,'--policy',policy)
    assert code==0
    seam=next(s for s in report['seams'] if s['source']['qualified_symbol']=='z93')
    assert seam['eligibility']=='ineligible' and 'hard_real_time_exclusion' in seam['reasons']
    cfg=copy.deepcopy(DEFAULT);cfg['repository']['exclude'].append('opaque.py')
    config=save(outside/'configuration.json',cfg)
    code,report=invoke(host,'--config',config)
    assert code==0 and report['seams']==[]


@pytest.mark.parametrize('option',['--config','--policy'])
def test_configuration_symlink_loop_has_redacted_failure(fixture,capsys,option):
    host,outside=fixture
    loop=outside/'PRIVATE_CONFIGURATION_LOOP';loop.symlink_to(loop.name)
    assert cli.main(['repository-discovery',str(host),option,str(loop),'--out',str(outside/'out.json')])==2
    output=capsys.readouterr()
    assert json.loads(output.out)=={'status':'blocked','reason':'input_unavailable_or_invalid'}
    assert not output.err and 'PRIVATE_CONFIGURATION_LOOP' not in output.out


@pytest.mark.parametrize("script,args", [
    ("prepare_repository_inventory.py", ["--unexpected", "SENSITIVE-ARGUMENT"]),
    ("prepare_repository_inventory.py", ["--stage", "SENSITIVE-ARGUMENT"]),
    ("prepare_repository_inventory.py", ["SENSITIVE-ARGUMENT"]),
    ("prepare_repository_inventory.py", ["--capabilities"]),
])
def test_argument_errors_never_echo_untrusted_values(fixture, script, args):
    prefix = [str(fixture[0])]
    run = subprocess.run([sys.executable, "-I", str(ROOT/"scripts"/script), *prefix, *args],
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 2 and run.stderr == ""
    assert json.loads(run.stdout) == {"status":"blocked", "reason":"invalid_command_arguments"}
