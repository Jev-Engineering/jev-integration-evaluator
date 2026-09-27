"""Generate and run the v1.1 lifecycle entirely offline using explicitly synthetic evidence."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_integration_evaluator.cli import main as cli
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import InputError, digest, read_json, read_jsonl, write_json
from jev_integration_evaluator.traces import AuditLog


def run_demo(out: Path) -> dict:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise InputError('Choose a new or empty output directory for the synthetic demonstration')
    commands = []
    def invoke(*args, expected=0):
        argv = [str(a) for a in args]
        code = cli(argv)
        commands.append({'command': argv, 'exit_code': code})
        if code != expected:
            raise InputError('Offline demo command returned an unexpected exit status')
    cfg = load_config()
    cfg['validation'].update(bootstrap_samples=250, bayesian_samples=500)
    write_json(out / 'demo-config.json', {'jev_analysis': cfg})

    # Rescans use a temporary fixture, never a user's repository.
    with tempfile.TemporaryDirectory(prefix='jev-synthetic-diff-') as temp:
        repo = Path(temp) / 'synthetic-agent'
        shutil.copytree(ROOT / 'examples/coding-agent', repo)
        invoke('scan', '--repo', repo, '--out', out / 'before', '--config', out / 'demo-config.json')
        (repo / 'pyproject.toml').write_text('[project]\nname = "synthetic-diff-fixture"\nversion = "0.0.0"\n')
        invoke('scan', '--repo', repo, '--out', out / 'after', '--config', out / 'demo-config.json')
        invoke('diff', '--before', out / 'before/jev-opportunities.json', '--after', out / 'after/jev-opportunities.json',
               '--out', out / 'snapshot-diff.json')

    baseline = read_jsonl(ROOT / 'examples/research/baseline.jsonl')
    treatment = read_jsonl(ROOT / 'examples/research/router-verifier.jsonl')
    arm_fields = ('treatment', 'code_revision', 'model_id', 'policy_version', 'prompt_hash', 'mode')
    spec = {'experiment_id': 'synthetic-v11-demo', 'dataset_id': baseline[0]['dataset_id'],
            'evidence_type': 'synthetic', 'primary_metric': 'success',
            'schedule': [{'task_id': b['task_id'], 'replicate': b['replicate'], 'task_hash': b['task_hash'],
                          'cluster_id': b['task_id'], 'seed': b['seed'], 'split': 'test'} for b in baseline],
            'baseline': {k: baseline[0][k] for k in arm_fields},
            'jev': {k: treatment[0][k] for k in arm_fields},
            'required_metrics': ['latency_ms', 'cost', 'unsafe_actions', 'false_blocks']}
    write_json(out / 'study-spec.json', spec)
    invoke('study-freeze', '--spec', out / 'study-spec.json', '--out', out / 'study.json',
           '--config', out / 'demo-config.json')
    plan = read_json(out / 'study.json')
    for rows in (baseline, treatment):
        for r in rows:
            r.update(experiment_id=spec['experiment_id'], study_digest=plan['contract_digest'],
                     split='test', cluster_id=r['task_id'], run_status='completed')
    write_json(out / 'baseline.json', baseline); write_json(out / 'treatment.json', treatment)
    for command in ('study-check', 'study-evaluate'):
        invoke(command, '--plan', out / 'study.json', '--baseline', out / 'baseline.json', '--jev', out / 'treatment.json',
               '--expected-digest', plan['contract_digest'], '--out', out / (command + '.json'))

    questions = {'action': {'type': 'choice', 'instructions': 'Select the evidence-supported criterion.',
                           'criteria': {'inspect': 'Evidence supports additional inspection.',
                                        'stop': 'Evidence supports stopping.'}}}
    def observation(i, split):
        return {'observation_id': f'{split}-{i}', 'task_hash': digest([split, i]),
                'cluster_id': f'{split}-{i}', 'subgroup': 'ordinary', 'kind': 'choice', 'split': split,
                'model_id': cfg['runtime']['model'], 'policy_version': 'synthetic-v11', 'rubric_hash': digest(questions),
                'evidence_type': 'synthetic', 'choice': 'inspect', 'probabilities': {'inspect': .99, 'stop': .01},
                'confidence': .95, 'label': 'inspect'}
    calibration = [observation(i, 'calibration') for i in range(40)]
    holdout = [observation(i, 'test') for i in range(120)]
    threshold_spec = {'probability_floor': .90, 'confidence_floor': .75, 'action_probability_floors': {},
                      'abstention_labels': [], 'maximum_error': .05, 'alpha': .05, 'minimum_accepted': 30,
                      'required_subgroups': ['ordinary'],
                      'holdout_schedule': [{k: r[k] for k in ('observation_id', 'task_hash', 'cluster_id', 'subgroup')} for r in holdout]}
    write_json(out / 'calibration.json', calibration); write_json(out / 'holdout.json', holdout)
    write_json(out / 'threshold-spec.json', threshold_spec)
    invoke('threshold-freeze', '--input', out / 'calibration.json', '--spec', out / 'threshold-spec.json', '--out', out / 'threshold-policy.json')
    invoke('threshold-check', '--input', out / 'holdout.json', '--plan', out / 'threshold-policy.json',
           '--out', out / 'holdout-report.json', '--enforce', expected=3)

    event = {'state': {'evidence': 'SYNTHETIC: additional inspection is warranted.'}, 'questions': questions,
             'primary_question': 'action', 'model': cfg['runtime']['model'], 'ground_truth': 'inspect'}
    write_json(out / 'probe-event.json', event); write_json(out / 'questions.json', questions)
    invoke('rubric-lint', '--input', out / 'questions.json', '--out', out / 'rubric-lint.json')
    invoke('robustness-plan', '--input', out / 'probe-event.json', '--out', out / 'probe-suite.json')
    suite = read_json(out / 'probe-suite.json'); records = []
    for probe in suite['probes']:
        selected = next(k for k, canonical in probe['label_to_original'].items() if canonical == 'inspect')
        response = {'model': suite['model'], 'answers': {'action': {
                    'type': 'choice', 'choice': selected, 'confidence': .95,
                    'probabilities': {k: .99 if k == selected else .01 for k in probe['label_to_original']}}},
                    'usage': {'input_tokens': 20, 'output_tokens': 0}}
        records.append({'probe_id': probe['probe_id'], 'request_hash': probe['request_hash'], 'status': 'completed',
                        'evidence_type': 'synthetic', 'response': response})
    write_json(out / 'probe-records.json', records)
    write_json(out / 'probe-fixtures.json', {r['request_hash']: r['response'] for r in records})
    invoke('robustness-run', '--plan', out / 'probe-suite.json', '--fixtures', out / 'probe-fixtures.json', '--out', out / 'robustness-run.json')
    invoke('robustness-report', '--plan', out / 'probe-suite.json', '--input', out / 'probe-records.json', '--out', out / 'robustness-report.json')
    log = AuditLog(out / 'audit.jsonl')
    for i in range(3): log.append({'type': 'synthetic_demo', 'index': i, 'evidence_type': 'synthetic'})
    last = read_jsonl(out / 'audit.jsonl')[-1]['event_hash']
    write_json(out / 'audit-checkpoint.json', {'expected_events': 3, 'expected_final_hash': last})
    invoke('verify-log', '--input', out / 'audit.jsonl', '--expected-events', 3, '--expected-final-hash', last,
           '--out', out / 'audit-verification.json')
    for kind, filename in (('study-spec', 'study-spec.json'), ('study', 'study.json'),
                           ('threshold-spec', 'threshold-spec.json'), ('threshold-policy', 'threshold-policy.json'),
                           ('holdout-report', 'holdout-report.json'), ('robustness-suite', 'probe-suite.json')):
        invoke('validate', '--kind', kind, '--input', out / filename)
    summary = {'version': '1.1.0', 'evidence_type': 'synthetic', 'network_requests': 0,
               'host_actions_executed': 0, 'task_pairs': len(baseline), 'calibration_observations': len(calibration),
               'holdout_observations': len(holdout), 'robustness_probes': 5,
               'threshold_enforcement_exit': 3, 'commands': commands,
               'study_recommendation': read_json(out / 'study-evaluate.json')['recommendation'],
               'holdout_eligible_for_activation': read_json(out / 'holdout-report.json')['eligible_for_activation']}
    write_json(out / 'demo-summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='New or empty output directory')
    args = parser.parse_args(argv)
    try:
        result = run_demo(args.out)
        print(json.dumps({k: v for k, v in result.items() if k != 'commands'}, indent=2))
        return 0
    except (InputError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
