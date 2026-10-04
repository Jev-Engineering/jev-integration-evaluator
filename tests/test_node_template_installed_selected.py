"""Real npm-installed normal commands; finite offline synthetic receipts only."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import venv

import pytest

from jev_integration_evaluator.io import digest, file_hash, read_json
from jev_integration_evaluator import template_node_installation as installer
from jev_integration_evaluator.template_js_catalog import _source_tree
from test_js_template_delivery import request_for
from test_node_template_installation import native_tools
from test_node_template_installed_upgrade import (
    NODE_SHA256, NPM_CLI_SHA256, NPM_TREE_SHA256, TRUSTED_TYPESCRIPT_TREE_SHA256)

PROJECT = Path(__file__).resolve().parents[1]

# These host files, schedules and independent raw observations are authored
# before transformation. They never read an API key or open provider sockets.
START = '''const fs = require('node:fs');
const runtime = require('./jev_runtime.cjs');
const adapter = require('./jev_adapter.cjs');
const scenario = process.env.OFFLINE_SCENARIO;
const allowed = ['selected','denied','abstain','reject','late','cancel','revoke','malformed','replay','shared','executor_reject'];
if (!allowed.includes(scenario)) throw Error('unsupported authored scenario');
const output = process.env.OFFLINE_OBSERVATION;
const note = (role, value) => fs.appendFileSync(output + '.' + role, value + '\\n');
globalThis.__jev_probe_effect = (action, item) => { note('effects', action + ':' + item);
  if (scenario === 'executor_reject') throw Error('authored_executor_rejection'); };
const controller = new AbortController();
const request = {task_id:'task',invocation_id:'first',item:'alpha',permit:scenario !== 'denied',signal:controller.signal};
let attempts = 0;
const client = {evidence_type:'synthetic', evaluate:async () => {
  attempts++; note('requests','attempt');
  if (scenario === 'cancel') { controller.abort(); return {choice:{label:'summary',confidence:1}}; }
  if (scenario === 'revoke') request.permit = false;
  if (scenario === 'reject') throw Error('authored offline rejection');
  if (scenario === 'late') await new Promise(resolve=>setTimeout(resolve,100));
  if (scenario === 'malformed') return {choice:{label:'unknown',confidence:1}};
  return {choice:{label:scenario === 'abstain' ? 'uncertain' : 'summary',confidence:1}};
}};
const now = () => Date.parse('2026-09-28T00:00:00Z');
const limits = {max_calls:1,max_cost:1,max_tasks:10000,max_calls_per_task:1};
let secondAdapter = null, secondSeam = null;
if (scenario === 'shared') {
  const secondRoot = process.env.OFFLINE_SECOND_PACKAGE;
  secondAdapter = require(secondRoot + '/jev_adapter.cjs');
  secondSeam = require(secondRoot + '/host.cjs');
}
const ownerFault = process.env.OFFLINE_OWNER_FAULT || 'none';
if (!['none','forged','unreviewed'].includes(ownerFault)) throw Error('unsupported owner fault');
const specHashes = secondAdapter ? [runtime.digest(adapter.SPEC),ownerFault === 'unreviewed' ? 'a'.repeat(64) : runtime.digest(secondAdapter.SPEC)] : null;
const owner = specHashes ? runtime.createRuntimeOwner({specHashes,limits,ledgerPath:process.env.OFFLINE_LEDGER}) : null;
const budget = owner ? null : new runtime.DurableSharedBudget({limits,ledgerPath:process.env.OFFLINE_LEDGER,
  identity:runtime.digest({spec:adapter.SPEC,limits})});
function initialize(target) {
  const activation = {runtime_contract_sha256:runtime.digest({spec:target.SPEC,budget_limits:limits}),
    source_sha256:target.SPEC.executed_source_sha256,canary_scope:target.SPEC.runtime.canary_scope,
    issued_at:'2026-09-27T23:59:00Z',expires_at:'2026-09-28T00:01:00Z'};
  target.initialize({mode:'active',client,budget:budget || undefined,runtimeOwner:ownerFault === 'forged' ? {...owner} : owner || undefined,
    now,activation,trusted_activation_sha256:runtime.digest(activation),
    audit:{append:event=>note('audit',event.kind)}});
}
initialize(adapter);
if (secondAdapter) initialize(secondAdapter);
SEAM_IMPORT
async function main() {
  try {
    const result = await seam(request);
    note('outcomes',result);
    if (scenario === 'replay') {
      try { await seam(request); note('outcomes','replayed'); }
      catch(error) { note('outcomes',error.code || error.message); }
    }
    if (secondSeam) {
      const result = await secondSeam({...request,task_id:'task-second',invocation_id:'second',item:'beta'});
      note('outcomes',result);
    }
  } catch(error) { note('outcomes',error.code || error.message); }
  await new Promise(resolve=>setTimeout(resolve,120));
  note('accounting',JSON.stringify(owner ? owner.status() : {calls:budget.calls,cost:budget.cost}));
  if (owner) owner.close(); else budget.close();
}
main().catch(()=>{process.exitCode=1;});
'''


@pytest.fixture
def native_install_tools(tmp_path):
    tools = native_tools()
    source = Path(os.environ.get('JEV_TRUSTED_TYPESCRIPT_PACKAGE', '/nonexistent'))
    wheelhouse = os.environ.get('JEV_TEMPLATE_WHEELHOUSE')
    if tools is None or not source.is_dir() or not wheelhouse:
        pytest.skip('exact native Node/npm, trusted TypeScript and reviewed offline wheelhouse required')
    node, npm = tools
    assert file_hash(node) == NODE_SHA256 and file_hash(npm) == NPM_CLI_SHA256
    assert digest(installer._tree(npm.parent.parent)) == NPM_TREE_SHA256
    assert digest(installer._tree(source)) == TRUSTED_TYPESCRIPT_TREE_SHA256
    tooling = tmp_path / 'tooling'
    (tooling / 'node_modules').mkdir(parents=True)
    os.chmod(tooling, 0o700)
    shutil.copytree(source, tooling / 'node_modules/typescript')
    (tmp_path / 'cache').mkdir(mode=0o700)
    (tmp_path / 'generations').mkdir(mode=0o700)
    wheel = tmp_path / 'wheel'; wheel.mkdir()
    built = subprocess.run([sys.executable,'-m','pip','wheel','--no-build-isolation','--no-deps',
                            '-w',str(wheel),str(PROJECT)],capture_output=True,text=True,timeout=120)
    assert built.returncode == 0, built.stderr[-1000:]
    environment = tmp_path / 'evaluator'
    venv.EnvBuilder(with_pip=False).create(environment)
    installed = subprocess.run([sys.executable,'-m','pip','--python',str(environment / 'bin/python'),
        'install','--no-index','--find-links',wheelhouse,str(next(wheel.glob('*.whl')))],
        capture_output=True,text=True,timeout=120)
    assert installed.returncode == 0, installed.stderr[-1000:]
    cli = environment / 'bin/jev-integration-evaluator'

    def invoke(*args, okay=True):
        run = subprocess.run([str(cli),*map(str,args)],cwd=tmp_path,
            env={'PATH':str(node.parent)+':/usr/bin:/bin','PYTHONNOUSERSITE':'1'},
            capture_output=True,text=True,timeout=120)
        if not okay:
            assert run.returncode == 2 and not run.stdout
            return json.loads(run.stderr)
        assert run.returncode == 0, run.stderr[-1000:]
        return json.loads(run.stdout)
    return node,npm,tooling,invoke


def installed_selected_host(tmp_path, tools, fmt, name='first'):
    node,npm,tooling,invoke = tools
    work=tmp_path / name; work.mkdir(mode=0o700)
    source,request=request_for(work,fmt)
    host=source / request['implementation_spec']['source']['file']
    text=host.read_text()
    text=text.replace('function hostRegistry(request) { return {read: original}; }',
        "async function summarize(request) { globalThis.__jev_probe_effect?.('summary',request.item); return 'summary:' + request.item; }\n"
        "function hostRegistry(request) { return {read:original,summarize}; }")
    text=text.replace("allowed_actions: ['read']","allowed_actions: ['read','summarize']")
    text += '\nfunction hostOptions(request) { return {signal: request.signal}; }\n'
    host.write_text(text)
    spec=request['implementation_spec']; spec['source']['sha256']=file_hash(host)
    spec['candidate_id']='authored-offline-'+name
    spec['bindings']['invocation_options']='hostOptions'
    spec['runtime']['registered_action_ids']=['read','summarize']
    spec['runtime']['questions']['choice']['criteria']['summary']='Summarize'
    spec['runtime']['label_actions']['summary']='summarize'
    entry='start.cjs' if fmt=='commonjs' else 'start.mjs'
    seam=("const seam = require('./host.cjs');" if fmt=='commonjs' else "const {seam} = await import('./host.mjs');")
    # ESM uses createRequire solely in independently authored entrypoint; target
    # transform remains the bounded static one-tail-call source without imports.
    start=START.replace('SEAM_IMPORT',seam)
    if fmt!='commonjs':
        start="import {createRequire} from 'node:module';\nconst require=createRequire(import.meta.url);\n"+start
    (source / entry).write_text(start)
    for filename in ('package.json','package-lock.json'):
        path=source / filename; data=read_json(path); data['name']='authored-selected-'+name
        if filename=='package.json': data['scripts']['start']='node '+entry
        else: data['packages']['']['name']=data['name']
        path.write_text(json.dumps(data))
    request.update(entrypoint=entry,entrypoint_sha256=file_hash(source / entry),
        package_json_sha256=file_hash(source / 'package.json'),
        package_lock_sha256=file_hash(source / 'package-lock.json'),
        reviewed_package_source_sha256=digest(_source_tree(source)))
    cases=[{'id':'baseline','request':{'task_id':'task','invocation_id':'baseline','item':'alpha','permit':True},
        'result':'read:alpha','events':[['read','alpha']],'effects':[['read','alpha']]}]
    spec['verification_sha256']=digest(cases); spec['verification_cases_count']=1

    def save(label,data):
        path=tmp_path / (name+'-'+label+'.json'); path.write_text(json.dumps(data)); return path
    rendered=tmp_path / (name+'-render')
    invoke('template','materialize','--repo',source,'--request',save('request',request),
           '--out',rendered,'--tooling',tooling)
    bundle=tmp_path / (name+'-bundle')
    planned=invoke('js-plan','--repo',source,'--spec',rendered / 'implementation-spec.json',
                   '--bundle',bundle,'--tooling',tooling)
    casefile=save('cases',cases)
    baseline=invoke('js-verify','--repo',source,'--bundle',bundle,'--phase','baseline',
        '--cases',casefile,'--approve-execution','--tooling',tooling)
    invoke('js-apply','--repo',source,'--bundle',bundle,'--approve',planned['bundle_sha256'],
        '--baseline-sha256',baseline['receipt_sha256'],'--tooling',tooling)
    modified=invoke('js-verify','--repo',source,'--bundle',bundle,'--phase','modified',
        '--cases',casefile,'--approve-execution','--baseline-sha256',baseline['receipt_sha256'],'--tooling',tooling)
    package_request={'schema_version':'1.0','kind':'node-package-request-v1','host_root':str(source),
        'render_directory':str(rendered),'implementation_bundle':str(bundle),
        'trusted_modified_sha256':modified['receipt_sha256'],'node':str(node),'node_sha256':file_hash(node),
        'npm_cli':str(npm),'npm_cli_sha256':file_hash(npm),'npm_tree_sha256':digest(installer._tree(npm.parent.parent)),
        'tooling_directory':str(tooling),'offline_cache':str(tmp_path / 'cache'),
        'package_directory':str(tmp_path / (name+'-package')),'environment_parent':str(tmp_path / 'generations')}
    package_plan=tmp_path / (name+'-package-plan.json')
    pp=invoke('template','node-package-plan','--request',save('package-request',package_request),'--out',package_plan)
    packaged=invoke('template','node-package-build','--plan',package_plan,'--approve-plan-sha256',pp['plan_sha256'])
    install_plan=tmp_path / (name+'-install-plan.json')
    ip=invoke('template','node-install-plan','--package-plan',package_plan,
        '--package-receipt',Path(package_request['package_directory']) / 'package-receipt.json',
        '--trusted-package-receipt-sha256',packaged['receipt_sha256'],'--out',install_plan)
    installed=invoke('template','node-install','--plan',install_plan,'--approve-plan-sha256',ip['plan_sha256'])
    receipt=read_json(Path(installed['generation_path']) / 'install-receipt.json') if 'generation_path' in installed else read_json(
        tmp_path / 'generations' / ('jev-node-env-'+ip['plan_sha256'][:24]) / 'install-receipt.json')
    return receipt,package_plan,install_plan,invoke


def lines(path):
    return path.read_text().splitlines() if path.exists() else []


@pytest.mark.parametrize('fmt',['commonjs','esm','typescript'])
def test_installed_normal_selected_fallback_denied_cancel_and_replay(tmp_path,native_install_tools,fmt):
    receipt,_,_,_=installed_selected_host(tmp_path,native_install_tools,fmt)
    node=native_install_tools[0]
    schedule={
        'selected':(['summary:alpha'],['summary:alpha']),
        'denied':([],['blocked']), 'abstain':(['read:alpha'],['read:alpha']),
        'reject':(['read:alpha'],['read:alpha']), 'late':(['read:alpha'],['read:alpha']),
        'malformed':(['read:alpha'],['read:alpha']), 'revoke':([],['blocked']),
        'cancel':([],['cancelled']), 'executor_reject':(['summary:alpha'],['authored_executor_rejection']), 'replay':(['summary:alpha'],['summary:alpha','effect_replay_denied'])}
    for scenario,(effects,outcomes) in schedule.items():
        prefix=tmp_path / ('observation-'+scenario); parent=tmp_path / ('ledger-'+scenario); parent.mkdir(mode=0o700)
        run=subprocess.run(receipt['command'],cwd=receipt['working_directory'],env={
            'PATH':str(node.parent)+':/usr/bin:/bin','OFFLINE_SCENARIO':scenario,
            'OFFLINE_OBSERVATION':str(prefix),'OFFLINE_LEDGER':str(parent / 'runtime.sqlite')},
            capture_output=True,text=True,timeout=20)
        assert run.returncode==0,run.stderr
        assert lines(Path(str(prefix)+'.effects'))==effects
        assert lines(Path(str(prefix)+'.outcomes'))==outcomes
        assert lines(Path(str(prefix)+'.requests'))==['attempt']
        accounting=json.loads(lines(Path(str(prefix)+'.accounting'))[0])
        assert accounting['calls']==accounting['cost']==1
        audit=lines(Path(str(prefix)+'.audit'))
        assert audit[0]=='assessment_intent'
        if scenario=='cancel':
            assert audit==['assessment_intent']
        elif scenario in ('denied','revoke'):
            assert audit==['assessment_intent','blocked']
        elif scenario in ('selected','replay','executor_reject'):
            assert audit==['assessment_intent','effect_intent']
        else:
            assert audit==['assessment_intent','baseline_intent']
        if scenario in ('late','reject','cancel','executor_reject'):
            restarted=tmp_path / ('restart-'+scenario)
            run=subprocess.run(receipt['command'],cwd=receipt['working_directory'],env={
                'PATH':str(node.parent)+':/usr/bin:/bin','OFFLINE_SCENARIO':'selected',
                'OFFLINE_OBSERVATION':str(restarted),'OFFLINE_LEDGER':str(parent / 'runtime.sqlite')},
                capture_output=True,text=True,timeout=20)
            assert run.returncode!=0 and 'runtime_ledger_unresolved_or_revoked' in run.stderr
            assert lines(Path(str(restarted)+'.effects'))==[]
            assert lines(Path(str(restarted)+'.requests'))==[]
    assert receipt['mode']=='off' and receipt['runtime_activation_authorized'] is False
    # Drifted installed source refuses before every possible selected/fallback
    # effect. Restoring bytes is test cleanup, never adoption of drifted source.
    installed_host=Path(receipt['working_directory']) / ('host.ts' if fmt=='typescript' else 'host.cjs' if fmt=='commonjs' else 'host.mjs')
    original=installed_host.read_bytes(); installed_host.write_bytes(original+b'\n// authored source drift\n')
    prefix=tmp_path / 'source-drift-observation'; parent=tmp_path / 'source-drift-ledger'; parent.mkdir(mode=0o700)
    try:
        run=subprocess.run(receipt['command'],cwd=receipt['working_directory'],env={
            'PATH':str(node.parent)+':/usr/bin:/bin','OFFLINE_SCENARIO':'selected',
            'OFFLINE_OBSERVATION':str(prefix),'OFFLINE_LEDGER':str(parent / 'runtime.sqlite')},
            capture_output=True,text=True,timeout=20)
        assert run.returncode!=0 and 'applied_host_source_changed' in run.stderr
        assert lines(Path(str(prefix)+'.effects'))==[]
        assert lines(Path(str(prefix)+'.requests'))==[]
    finally:
        installed_host.write_bytes(original)


def test_two_installed_placements_share_one_durable_owner_and_retained_limit(tmp_path,native_install_tools):
    first,_,_,_=installed_selected_host(tmp_path,native_install_tools,'commonjs','first')
    second,_,_,_=installed_selected_host(tmp_path,native_install_tools,'commonjs','second')
    node=native_install_tools[0]
    parent=tmp_path / 'shared-ledger'; parent.mkdir(mode=0o700)
    prefix=tmp_path / 'shared-observation'
    environment={'PATH':str(node.parent)+':/usr/bin:/bin','OFFLINE_SCENARIO':'shared',
        'OFFLINE_OBSERVATION':str(prefix),'OFFLINE_LEDGER':str(parent / 'runtime.sqlite'),
        'OFFLINE_SECOND_PACKAGE':second['working_directory']}
    run=subprocess.run(first['command'],cwd=first['working_directory'],env=environment,
                       capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    assert lines(Path(str(prefix)+'.effects'))==['summary:alpha','read:beta']
    assert lines(Path(str(prefix)+'.requests'))==['attempt']
    assert lines(Path(str(prefix)+'.outcomes'))==['summary:alpha','read:beta']
    accounting=json.loads(lines(Path(str(prefix)+'.accounting'))[0])
    assert accounting=={'calls':1,'cost':1,'suspended':False,'placements_bound':2,
                       'evidence_type':'synthetic_installed_protocol'}
    with closing(sqlite3.connect(parent / 'runtime.sqlite')) as database:
        state=json.loads(database.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
    assert len(state['invocations'])==2 and state['calls']==state['cost']==1
    assert state['pending']==[]
    prefix=tmp_path / 'reopen-observation'
    environment['OFFLINE_OBSERVATION']=str(prefix)
    run=subprocess.run(first['command'],cwd=first['working_directory'],env=environment,
                       capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    assert lines(Path(str(prefix)+'.effects'))==[]
    assert lines(Path(str(prefix)+'.requests'))==[]
    assert lines(Path(str(prefix)+'.outcomes'))==['effect_replay_denied']
    for fault,expected in [('forged','runtime_owner_identity_mismatch'),
                           ('unreviewed','runtime_owner_placement_mismatch')]:
        prefix=tmp_path / (fault+'-observation'); ledger_parent=tmp_path / (fault+'-ledger'); ledger_parent.mkdir(mode=0o700)
        rejected_environment={**environment,'OFFLINE_OBSERVATION':str(prefix),
            'OFFLINE_LEDGER':str(ledger_parent / 'runtime.sqlite'),'OFFLINE_OWNER_FAULT':fault}
        run=subprocess.run(first['command'],cwd=first['working_directory'],env=rejected_environment,
                           capture_output=True,text=True,timeout=20)
        assert run.returncode!=0 and expected in run.stderr
        assert lines(Path(str(prefix)+'.effects'))==[]
        assert lines(Path(str(prefix)+'.requests'))==[]
    second_runtime=Path(second['working_directory']) / 'jev_runtime.cjs'
    original=second_runtime.read_bytes(); second_runtime.write_bytes(original+b'\n// authored runtime drift\n')
    prefix=tmp_path / 'runtime-drift-observation'; ledger_parent=tmp_path / 'runtime-drift-ledger'; ledger_parent.mkdir(mode=0o700)
    try:
        run=subprocess.run(first['command'],cwd=first['working_directory'],env={**environment,
            'OFFLINE_OBSERVATION':str(prefix),'OFFLINE_LEDGER':str(ledger_parent / 'runtime.sqlite')},
            capture_output=True,text=True,timeout=20)
        assert run.returncode!=0 and 'runtime_owner_code_mismatch' in run.stderr
        assert lines(Path(str(prefix)+'.effects'))==[]
        assert lines(Path(str(prefix)+'.requests'))==[]
    finally:
        second_runtime.write_bytes(original)


def test_installed_cli_toolchain_drift_and_owned_build_recovery(tmp_path,native_install_tools,monkeypatch):
    receipt,package_plan,_,invoke=installed_selected_host(tmp_path,native_install_tools,'commonjs')
    plan=read_json(package_plan)
    compiler=native_install_tools[2] / 'node_modules/typescript/lib/typescript.js'
    original=compiler.read_bytes()
    compiler.write_bytes(original+b'\n// authored trusted toolchain drift\n')
    try:
        refused=invoke('template','node-package-status','--plan',package_plan,
            '--trusted-receipt-sha256',read_json(Path(plan['request']['package_directory']) / 'package-receipt.json')['receipt_sha256'],
            okay=False)
        assert refused['status']=='rejected'
        assert not list(tmp_path.glob('*.effects'))
    finally:
        compiler.write_bytes(original)
    request=dict(plan['request'],package_directory=str(tmp_path / 'interrupted-package'))
    request_file=tmp_path / 'interrupted-request.json'; request_file.write_text(json.dumps(request))
    pending_plan=tmp_path / 'interrupted-plan.json'
    planned=invoke('template','node-package-plan','--request',request_file,'--out',pending_plan)
    reviewed=read_json(pending_plan)
    original_record=installer._record

    def interrupt(root,sha,event):
        if event=='build_complete':
            raise RuntimeError('authored offline build interruption')
        return original_record(root,sha,event)
    with monkeypatch.context() as patch:
        patch.setattr(installer,'_record',interrupt)
        with pytest.raises(RuntimeError,match='build interruption'):
            installer.build_node_package(reviewed,approved_plan_sha256=planned['plan_sha256'])
    status=invoke('template','node-package-status','--plan',pending_plan)
    assert status['status']=='build_interrupted_review_required'
    recovery_file=tmp_path / 'recovery-plan.json'
    recovery=invoke('template','node-package-recovery-plan','--plan',pending_plan,'--out',recovery_file)
    invoke('template','node-package-recover','--plan',pending_plan,'--recovery-plan',recovery_file,
        '--approve-plan-sha256',planned['plan_sha256'],'--approve-recovery-sha256','0'*64,okay=False)
    assert Path(request['package_directory']).is_dir()
    result=invoke('template','node-package-recover','--plan',pending_plan,'--recovery-plan',recovery_file,
        '--approve-plan-sha256',planned['plan_sha256'],'--approve-recovery-sha256',recovery['recovery_sha256'])
    assert result['status']=='owned_incomplete_package_removed'
    assert not Path(request['package_directory']).exists()
    assert Path(receipt['generation_path']).is_dir()
    # Recovery retains the interrupted attempt and a fresh exact approval builds
    # usable bytes; status or a retry never performs the removal itself.
    packaged=invoke('template','node-package-build','--plan',pending_plan,'--approve-plan-sha256',planned['plan_sha256'])
    assert packaged['receipt_sha256']
    assert installer._recovery_rows(Path(request['package_directory']))[-1]['event']=='recovery_complete'
    assert invoke('template','node-package-status','--plan',pending_plan,
        '--trusted-receipt-sha256',packaged['receipt_sha256'])['status']=='packaged_recorded'

    fresh_install=tmp_path / 'recovered-install-plan.json'
    ip=invoke('template','node-install-plan','--package-plan',pending_plan,
        '--package-receipt',Path(request['package_directory']) / 'package-receipt.json',
        '--trusted-package-receipt-sha256',packaged['receipt_sha256'],'--out',fresh_install)
    invoke('template','node-install','--plan',fresh_install,'--approve-plan-sha256',ip['plan_sha256'])
    installed_root=tmp_path / 'generations' / ('jev-node-env-'+ip['plan_sha256'][:24])
    fresh=read_json(installed_root / 'install-receipt.json')
    prefix=tmp_path / 'recovered-effects'; ledger_parent=tmp_path / 'recovered-ledger'; ledger_parent.mkdir(mode=0o700)
    run=subprocess.run(fresh['command'],cwd=fresh['working_directory'],env={
        'PATH':str(native_install_tools[0].parent)+':/usr/bin:/bin','OFFLINE_SCENARIO':'selected',
        'OFFLINE_OBSERVATION':str(prefix),'OFFLINE_LEDGER':str(ledger_parent / 'runtime.sqlite')},
        capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    assert lines(Path(str(prefix)+'.effects'))==['summary:alpha']
