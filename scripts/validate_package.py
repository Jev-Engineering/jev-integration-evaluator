"""Validate package contracts and examples locally; does not execute target code or use a model."""
from pathlib import Path
import argparse,hashlib,json,sys,re
import jsonschema,yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.io import InputError,read_json,read_jsonl,file_hash,write_json,safe_child
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.questions import validate_questions
from jev_integration_evaluator.client import FixtureClient
from jev_integration_evaluator.replay import replay_decisions


def validate(check_manifest=False):
    required=['SKILL.md','README.md','LICENSE','AGENTS.md','ONBOARDING.md','BRANDING.md','CONTRIBUTING.md','SECURITY.md','skill-package.json',
              'schemas/opportunity.schema.json','schemas/experiment.schema.json','schemas/decision.schema.json',
              'scripts/scan_repo.py','scripts/compare_runs.py','references/requirements-traceability.md',
              'references/placement-patterns.md','references/experimental-methodology.md','templates/jev-config.yaml',
              'examples/coding-agent/agent.py','examples/generic-service/service.py','tests/test_scanner.py',
              'CHANGELOG.md','references/lifecycle-and-evidence.md','scripts/run_v11_demo.py',
              'jev_integration_evaluator/lifecycle.py','jev_integration_evaluator/study.py','jev_integration_evaluator/holdout.py','jev_integration_evaluator/robustness.py',
              'schemas/study-spec.schema.json','schemas/study.schema.json','schemas/threshold-spec.schema.json',
              'schemas/threshold-policy.schema.json','schemas/holdout-report.schema.json','schemas/robustness-suite.schema.json',
              'jev_integration_evaluator/budget.py','jev_integration_evaluator/scenarios.py','jev_integration_evaluator/gates.py','jev_integration_evaluator/monitoring.py','jev_integration_evaluator/cohorts.py',
              'scripts/run_v12_demo.py','scripts/v12_fixtures.py','references/operational-evidence-v1.2.md',
              'schemas/scenario-spec.schema.json','schemas/deployment-gate.schema.json','schemas/gate-bundle.schema.json',
              'schemas/monitor-spec.schema.json','schemas/monitor.schema.json','schemas/monitor-outcome.schema.json',
              'tests/test_budget_runtime_v12.py','tests/test_scenarios_v12.py','tests/test_gates_v12.py',
              'tests/test_monitoring_v12.py','tests/test_cli_v12.py']
    for item in required:
        if not (ROOT/item).is_file():raise InputError('Required package file missing: '+item)
    front=(ROOT/'SKILL.md').read_text().split('---',2)
    if len(front)!=3:raise InputError('SKILL.md needs YAML frontmatter')
    metadata=yaml.safe_load(front[1])
    if metadata.get('name')!='jev-integration-evaluator' or not metadata.get('description'):raise InputError('Invalid skill metadata')
    from jev_integration_evaluator import __version__
    project_version=re.search(r'^version\s*=\s*"([^"]+)"', (ROOT/'pyproject.toml').read_text(),re.M)
    if (metadata.get('metadata',{}).get('version')!=__version__
            or read_json(ROOT/'skill-package.json')['version']!=__version__
            or not project_version or project_version.group(1)!=__version__):
        raise InputError('Release version metadata disagree')
    schemas={}
    for path in sorted((ROOT/'schemas').glob('*.schema.json')):
        schema=read_json(path);jsonschema.Draft202012Validator.check_schema(schema)
        if schema!=read_json(ROOT/'jev_integration_evaluator/data'/path.name):raise InputError('Packaged schema mismatch: '+path.name)
        schemas[path.name.removesuffix('.schema.json')]=schema
    cfg=load_config(ROOT/'templates/jev-config.yaml')
    jsonschema.validate({'jev_analysis':cfg},schemas['config'])
    fixture_records=0
    for path in (ROOT/'examples/research').glob('*.jsonl'):
        if path.name in ('decisions.jsonl',):kind='decision'
        elif path.name.startswith('calibration-'):continue
        else:kind='run'
        for row in read_jsonl(path):jsonschema.validate(row,schemas[kind]);fixture_records+=1
    for kind in ('study-spec','threshold-spec','scenario-spec','monitor-spec'):
        jsonschema.validate(read_json(ROOT/'templates'/(kind+'.example.json')),schemas[kind])
    jsonschema.validate(read_json(ROOT/'templates/activation-v1.2.example.json'),schemas['activation'])
    from jev_integration_evaluator.monitoring import freeze_monitor
    freeze_monitor(read_json(ROOT/'templates/monitor-spec.example.json'))
    event_path=ROOT/'examples/research/decisions.jsonl'
    result=replay_decisions(read_jsonl(event_path),FixtureClient(read_json(ROOT/'examples/research/fixture-responses.json')))
    if result['evaluation_failures']:raise InputError('Exact offline replay fixture failed')
    forbidden={'.pem','.key','.p12','.ttf','.otf','.woff','.woff2'}
    for p in ROOT.rglob('*'):
        if any(x in ('node_modules','.venv','.git','__pycache__','.pytest_cache','build','dist') or x.endswith('.egg-info') for x in p.relative_to(ROOT).parts):continue
        if p.is_symlink():raise InputError('Package contains a symlink: '+str(p.relative_to(ROOT)))
        if p.is_file() and (p.suffix in forbidden or p.name=='.env'):raise InputError('Secret/font asset must not be bundled: '+str(p.relative_to(ROOT)))
    checked=0
    if check_manifest:
        manifest=ROOT/'SHA256SUMS'
        if not manifest.exists():raise InputError('Release checksum manifest is absent')
        listed=set()
        for line in manifest.read_text().splitlines():
            expected,relative=line.split('  ',1)
            if not re.fullmatch('[a-f0-9]{64}',expected) or relative in listed:
                raise InputError('Malformed or duplicated release checksum entry')
            listed.add(relative)
            path=safe_child(ROOT,relative)
            if not path.is_file() or file_hash(path)!=expected:raise InputError('Checksum mismatch: '+relative)
            checked+=1
        def included(p):
            parts=p.relative_to(ROOT).parts
            return (p.is_file() and p.name!='SHA256SUMS' and p.suffix not in ('.pyc','.pyo','.zip','.whl')
                    and not any(x in ('node_modules','.venv','.git','__pycache__','.pytest_cache','build','dist')
                                or x.endswith('.egg-info') for x in parts))
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if included(p)}
        if actual != listed:
            raise InputError('Release manifest file set differs from package; added or missing files detected')
    return {'status':'passed','schema_count':len(schemas),'synthetic_records_validated':fixture_records,
            'offline_replay_decisions':result['evaluated'],'manifest_files_verified':checked,
            'network_requests':0,'target_code_executed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-manifest',action='store_true');p.add_argument('--out')
    a=p.parse_args()
    try:
        result=validate(a.check_manifest)
        if a.out:write_json(a.out,result)
        print(json.dumps(result,indent=2));return 0
    except Exception as exc:
        print('Validation failed: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
