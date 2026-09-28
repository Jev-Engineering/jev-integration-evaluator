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
              'tests/test_monitoring_v12.py','tests/test_cli_v12.py',
              'references/executable-integrations.md','scripts/run_implementation_demo.py','scripts/implementation_fixtures.py',
              'jev_integration_evaluator/integrations/recipes.py','jev_integration_evaluator/integrations/host.py',
              'jev_integration_evaluator/integrations/adaptation_shapes.py',
              'jev_integration_evaluator/integrations/adaptation_lifecycle.py',
              'jev_integration_evaluator/integrations/adaptation_review.py',
              'jev_integration_evaluator/integrations/adaptation_prerequisites.py',
              'schemas/offline-adaptation-proposal-v1.schema.json',
              'schemas/offline-adaptation-prerequisites-v1.schema.json',
              'schemas/adaptation-prerequisite-plan-v1.schema.json',
              'schemas/adaptation-request-v1.schema.json','schemas/adaptation-plan-v1.schema.json',
              'references/python-adaptation-v1.md',
              'tests/test_adaptation_shapes.py','tests/test_adaptation_lifecycle.py','tests/test_adaptation_native.py',
              'tests/test_adaptation_review.py','tests/test_adaptation_prerequisites.py',
              'tests/test_adaptation_prerequisite_native.py',
              'jev_integration_evaluator/integrations/lifecycle.py','jev_integration_evaluator/integrations/verification.py',
              'schemas/implementation-spec.schema.json','schemas/implementation-plan.schema.json','schemas/implementation-receipt.schema.json',
              'schemas/implementation-manifest.schema.json','schemas/implementation-tests.schema.json',
              'tests/test_executable_recipes.py','tests/test_executable_runtime.py','tests/test_executable_safety.py','tests/test_executable_cli.py','tests/test_executable_wheel.py',
              'tests/test_executable_host_boundaries.py','tests/test_executable_source_scope.py','tests/test_executable_verification_identity.py',
              'jev_integration_evaluator/integrations/runtime_lifecycle.py',
              'tests/test_host_runtime_lifecycle.py', 'references/host-runtime-lifecycle.md',
              'validation/REPOSITORY-SESSION-VALIDATION-1.3.0.dev11.md',
              'jev_integration_evaluator/integrations/observations.py','schemas/implementation-observation.schema.json',
              'tests/test_executable_failure_receipts.py','tests/test_executable_source_fidelity.py','tests/test_executable_command_receipts.py',
              'examples/implementation/observation.example.json',
              'jev_integration_evaluator/capabilities.py','scripts/discover_capabilities.py','references/capabilities.md',
              'schemas/repository-capabilities.schema.json','schemas/candidate-nomination.schema.json','schemas/admitted-nomination.schema.json',
              'tests/test_capabilities.py','tests/test_capabilities_adversarial.py','tests/test_capabilities_examples.py',
              'tests/test_capabilities_cli.py','tests/test_capabilities_wheel.py',
              'examples/capabilities/report.example.json','examples/capabilities/nomination.example.json',
              'examples/capabilities/admitted.example.json','examples/capabilities/opaque_host/opaque.py']
    required += ['jev_integration_evaluator/nomination_inventory.py',
                 'jev_integration_evaluator/repository_discovery.py',
                 'scripts/prepare_repository_inventory.py', 'scripts/run_capability_demo.py',
                 'references/repository-discovery-v1.md',
                 'tests/test_nomination_inventory.py', 'tests/test_repository_discovery_cli.py',
                 'tests/test_repository_discovery_wheel.py', 'tests/test_capabilities_bridge_guards.py',
                 'tests/test_review_gate_invariants.py', 'references/review-gate-invariants.md']
    required += ['jev_integration_evaluator/selection.py',
                 'scripts/select_placement.py', 'scripts/run_selection_demo.py',
                 'references/experimental-selection.md',
                 'tests/test_placement_selection.py', 'tests/test_placement_selection_cli.py',
                 'tests/test_placement_selection_wheel.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('placement-estimates', 'placement-interaction',
                              'placement-selection-envelope', 'placement-selection-request',
                              'placement-selection-summary', 'placement-selection')]
    required += ['jev_integration_evaluator/placement_selection.py',
                 'scripts/select_repository_placements.py',
                 'scripts/run_placement_selection_demo.py',
                 'scripts/build_placement_selection_schemas.py',
                 'references/placement-selection-v1.md',
                 'tests/test_repository_placement_selection.py',
                 'tests/test_repository_placement_wheel.py',
                 'tests/test_scope_review_conflicts.py',
                 'tests/test_placement_review_consistency.py',
                 'tests/test_placement_review_consistency_cli.py',
                 'examples/placement-selection/host/opaque.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-placement-context-v1',
                              'repository-placement-review-v1',
                              'repository-placement-selection-v1',
                              'repository-scope-review-v1')]
    required += ['jev_integration_evaluator/repository_conclusion.py',
                 'scripts/conclude_repository.py',
                 'scripts/rebuild_repository_conclusion_schemas.py',
                 'scripts/run_repository_conclusion_demo.py',
                 'references/repository-conclusion-v1.md',
                 'tests/test_repository_conclusion.py',
                 'tests/test_repository_conclusion_cli.py',
                 'tests/test_repository_conclusion_wheel.py']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-coverage-review-v1', 'repository-conclusion-v1')]
    required += ['jev_integration_evaluator/repository_run.py',
                 'jev_integration_evaluator/agent_review.py',
                 'jev_integration_evaluator/repository_selection.py',
                 'scripts/run_repository.py', 'scripts/run_repository_session_demo.py',
                 'scripts/run_repository_session_mutations.py',
                 'references/repository-session-command.md',
                 'tests/test_repository_run.py', 'tests/test_repository_run_wheel.py',
                 'tests/test_repository_selection.py',
                 'tests/test_repository_offline_agent_review.py',
                 'references/agent-review-protocol-v1.md',
                 'examples/repository-session/context.example.json',
                 'examples/repository-session/scope-denied.example.json']
    required += ['tests/path_corpus/README.md', 'tests/path_corpus/generate_support.py',
                 'tests/path_corpus/supported_host/host.py',
                 'tests/path_corpus/supported_host/main.py',
                 'tests/path_corpus/supported_host/expected.json',
                 'tests/test_path_corpus_connected.py',
                 'tests/test_path_corpus_oracle.py',
                 'tests/test_path_corpus_mutations.py',
                 'validation/path-corpus-support-v1.json',
                 'validation/PATH-CORPUS-CURRENT-SUPPORT.md']
    required += [f'{directory}/{name}.schema.json'
                 for directory in ('schemas', 'jev_integration_evaluator/data')
                 for name in ('repository-run-context-v1', 'repository-run-scope-v1',
                              'repository-run-selection-v1',
                              'repository-session-v1', 'repository-offline-agent-review-v1')]
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
    jsonschema.validate(read_json(ROOT/'examples/repository-session/context.example.json'),
                        schemas['repository-run-context-v1'])
    denied_scope=read_json(ROOT/'examples/repository-session/scope-denied.example.json')
    jsonschema.validate(denied_scope,schemas['repository-run-scope-v1'])
    if any(denied_scope['grants'].values()):
        raise InputError('Repository session example must deny every grant')
    from jev_integration_evaluator.integrations.contracts import validate_spec, validate_inventory
    from jev_integration_evaluator.integrations.recipes import transform
    implementation_examples=0
    for letter in 'abcdefghijklm':
        example=ROOT/'examples/implementation'/letter
        spec=validate_spec(read_json(example/'binding.example.json'))
        validate_inventory(example/'target',read_json(example/'reviewed-inventory.example.json'),spec)
        transform(example/'target',spec)
        implementation_examples+=1
    jsonschema.validate(read_json(ROOT/'examples/implementation/observation.example.json'),schemas['implementation-observation'])
    from jev_integration_evaluator.capabilities import _digest as capability_digest
    capability_examples={}
    for name,kind in (('report','repository-capabilities'),('nomination','candidate-nomination'),('admitted','admitted-nomination')):
        value=read_json(ROOT/'examples/capabilities'/(name+'.example.json'))
        jsonschema.validate(value,schemas[kind]);capability_examples[name]=value
    report,nomination,admitted=(capability_examples[name] for name in ('report','nomination','admitted'))
    if (report['report_sha256']!=capability_digest({k:v for k,v in report.items() if k!='report_sha256'})
            or report['snapshot_sha256']!=capability_digest(report['files'])
            or nomination['report_sha256']!=report['report_sha256']
            or admitted['report_sha256']!=report['report_sha256']
            or admitted['nomination_sha256']!=capability_digest(nomination)
            or admitted['source']!=nomination['source']):
        raise InputError('Capability example provenance mismatch')
    selected=[s for s in report['seams'] if s['seam_id']==nomination['seam_id']]
    if len(selected)!=1 or selected[0]['source']!=nomination['source']:
        raise InputError('Capability example nomination differs from discovered source')
    for source in [s['source'] for s in report['seams']]:
        path=safe_child(ROOT/'examples/capabilities/opaque_host',source['file'])
        if file_hash(path)!=source['file_sha256'] or not 1<=source['start_line']<=source['end_line']<=len(path.read_bytes().splitlines()):
            raise InputError('Capability example source identity mismatch')
    from jev_integration_evaluator.io import digest
    bridge_examples = {}
    for name, kind in (('capabilities','repository-capabilities'), ('nomination','candidate-nomination'),
                       ('admission','admitted-nomination'), ('prepared','repository-nominated-inventory-v1'),
                       ('review','repository-semantic-review-v1'), ('reviewed','repository-reviewed-inventory-v1')):
        value=read_json(ROOT/'examples/repository-capabilities'/(name+'.example.json'))
        jsonschema.validate(value,schemas[kind]);bridge_examples[name]=value
    cap_report,proposal,admission,prepared,review,reviewed=(bridge_examples[name] for name in
        ('capabilities','nomination','admission','prepared','review','reviewed'))
    for value,key in ((prepared,'prepared_sha256'),(reviewed,'reviewed_sha256')):
        if value[key]!=digest({k:v for k,v in value.items() if k!=key}):
            raise InputError('Bridge example digest mismatch')
    bridge_seams=[s for s in cap_report['seams'] if s['seam_id']==proposal['seam_id']]
    if (cap_report['report_sha256']!=capability_digest({k:v for k,v in cap_report.items() if k!='report_sha256'})
            or cap_report['snapshot_sha256']!=capability_digest(cap_report['files'])
            or len(bridge_seams)!=1 or bridge_seams[0]['source']!=proposal['source']
            or proposal['report_sha256']!=cap_report['report_sha256']
            or prepared['report_sha256']!=cap_report['report_sha256']
            or prepared['nominations']!=[proposal] or prepared['admissions']!=[admission]
            or admission['nomination_sha256']!=capability_digest(proposal)
            or admission['report_sha256']!=cap_report['report_sha256']
            or admission['source']!=proposal['source']
            or review['prepared_sha256']!=prepared['prepared_sha256']
            or reviewed['prepared_sha256']!=prepared['prepared_sha256']
            or reviewed['report_sha256']!=cap_report['report_sha256']
            or reviewed['bridge_engine_sha256']!=prepared['bridge_engine_sha256']
            or reviewed['review_sha256']!=digest(review)):
        raise InputError('Bridge example provenance mismatch')
    for envelope in (prepared,reviewed):
        jsonschema.validate(envelope['inventory'],schemas['inventory'])
        if envelope['inventory_sha256']!=digest(envelope['inventory']):
            raise InputError('Bridge example inventory digest mismatch')
        for item in envelope['inventory']['files']:
            if file_hash(safe_child(ROOT/'examples/repository-capabilities/host',item['file']))!=item['sha256']:
                raise InputError('Bridge example source identity mismatch')
    scope_examples = ROOT/'examples/placement-selection'
    for name, kind in (('context','repository-placement-context-v1'),
                       ('negative-context','repository-placement-context-v1'),
                       ('selection-review','repository-placement-review-v1'),
                       ('selection','repository-placement-selection-v1'),
                       ('scope-review','repository-scope-review-v1')):
        jsonschema.validate(read_json(scope_examples/(name+'.json')), schemas[kind])
    scope_report=read_json(scope_examples/'report.json')
    scope_review=read_json(scope_examples/'scope-review.json')
    from jev_integration_evaluator.placement_selection import _engine_identity as selection_engine_identity
    if (read_json(scope_examples/'context.json')['selection_engine_sha256']!=selection_engine_identity()
            or read_json(scope_examples/'selection.json')['selection_engine_sha256']!=selection_engine_identity()):
        raise InputError('Repository scope example engine identity mismatch')
    if (not scope_report['files'] or
            any(file_hash(safe_child(scope_examples/'host',item['file']))!=item['sha256']
                for item in scope_report['files']) or
            len(scope_review['files'])!=len(scope_report['files']) or
            len(scope_review['seams'])!=len(scope_report['seams']) or
            read_json(scope_examples/'negative-context.json')['outcome']!='no_useful_placement'):
        raise InputError('Repository scope example source or review mismatch')
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
            'implementation_examples_validated_without_execution':implementation_examples,
            'synthetic_observation_examples_validated':1,
            'capability_examples_validated_without_execution':len(capability_examples),
            'bridge_examples_validated_without_execution':len(bridge_examples),
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
