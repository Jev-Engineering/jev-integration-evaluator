import copy,time,threading,json
from dataclasses import asdict
import pytest
from jev_integration_evaluator.io import InputError,digest,read_jsonl
from jev_integration_evaluator.client import validate_response,TypeSafeHTTPClient,FixtureClient,NoRedirect
from jev_integration_evaluator.runtime import SafeRouter,HostGate,Thresholds,rollback_check
from jev_integration_evaluator.replay import replay_decisions
from jev_integration_evaluator.traces import AuditLog,verify_log,cache_analysis

class Client:
    is_remote=False
    def __init__(self,response,delay=0,fail=False):self.response=response;self.calls=0;self.delay=delay;self.fail=fail;self.states=[]
    def evaluate(self,state,questions,model,timeout_ms):
        self.calls+=1;time.sleep(self.delay);self.states.append(copy.deepcopy(state))
        if self.fail:raise RuntimeError('secret error must not be logged')
        return copy.deepcopy(self.response)

def activation(cfg,event,thresholds=None):
    return dict(approved=True,calibration_validated=True,model=cfg['model'],policy_version='v1',questions_hash=digest(event['questions']),thresholds_hash=digest(asdict(thresholds or Thresholds())),holdout_evidence_ref='synthetic-unit-test-only')

def kwargs(event,**kw):
    out=dict(task_id='task',state=event['state'],questions=event['questions'],primary_question='action',evidence_question='sufficient',baseline_action='stop',gate=HostGate(('inspect','stop')))
    out.update(kw);return out

def router(client,cfg,event,**extra):
    config=cfg['runtime'];config['mode']='active'
    return SafeRouter(client,config,activation=activation(config,event),**extra)

def test_off_is_no_call(cfg,example_event,response):
    client=Client(response,fail=True)
    with SafeRouter(client,cfg['runtime']) as r:result=r.route(**kwargs(example_event))
    assert result.action=='stop' and client.calls==0

@pytest.mark.parametrize('gate,expected',[(HostGate(('inspect','stop'),hard_block=True),'block'),(HostGate(('inspect','stop'),approval_required=True),'request_approval'),(HostGate(('inspect',),baseline_permitted=False,hard_block=True),'block')])
def test_host_gates_before_model(cfg,example_event,response,gate,expected):
    client=Client(response)
    with router(client,cfg,example_event) as r:result=r.route(**kwargs(example_event,gate=gate))
    assert result.action==expected and client.calls==0

def test_active_proposes_never_executes(cfg,example_event,response):
    client=Client(response)
    with router(client,cfg,example_event) as r:result=r.route(**kwargs(example_event))
    assert result.action=='inspect' and 'not_execution_authorization' in result.reason
    assert client.calls==1

@pytest.mark.parametrize('field',['approved','calibration_validated','model','policy_version','questions_hash','thresholds_hash','holdout_evidence_ref'])
def test_activation_bound_to_exact_contract(cfg,example_event,response,field):
    client=Client(response);c=cfg['runtime'];c['mode']='active';receipt=activation(c,example_event);receipt[field]=False if field in ('approved','calibration_validated') else ''
    with SafeRouter(client,c,activation=receipt) as r:result=r.route(**kwargs(example_event))
    assert result.action=='stop' and client.calls==0

def test_threshold_changes_invalidate_activation(cfg,example_event,response):
    client=Client(response);c=cfg['runtime'];c['mode']='active'
    with SafeRouter(client,c,activation=activation(c,example_event),thresholds=Thresholds(probability_floor=.99)) as r:
        assert r.route(**kwargs(example_event)).reason=='activation_or_calibration_missing'
    assert client.calls==0

@pytest.mark.parametrize('mode',['low_probability','low_confidence','insufficient','abstain','illegal'])
def test_model_abstention_and_host_policy(cfg,example_event,response,mode):
    a=response['answers']['action'];gate=HostGate(('inspect','stop'))
    if mode=='low_probability':a['probabilities']={'inspect':.60,'stop':.30,'uncertain':.10}
    if mode=='low_confidence':a['confidence']=.01
    if mode=='insufficient':response['answers']['sufficient']['noul']=.01
    if mode=='abstain':a.update(choice='uncertain',probabilities={'inspect':.01,'stop':.01,'uncertain':.98})
    if mode=='illegal':gate=HostGate(('stop',))
    with router(Client(response),cfg,example_event) as r:result=r.route(**kwargs(example_event,gate=gate))
    assert result.source!='jev_assessment'
    if mode!='low_confidence':assert result.action=='stop'

def test_timeout_circuit_and_call_budget(cfg,example_event,response):
    cfg['runtime'].update(timeout_ms=1,circuit_failures=1)
    client=Client(response,delay=.01)
    with router(client,cfg,example_event) as r:
        first=r.route(**kwargs(example_event));second=r.route(**kwargs(example_event))
        assert first.action=='stop' and second.reason=='circuit_open' and r.stats['timeouts']==1
    assert client.calls==1

def test_task_budget_is_cumulative(cfg,example_event,response):
    cfg['runtime']['max_calls_per_task']=1;client=Client(response)
    with router(client,cfg,example_event) as r:
        r.route(**kwargs(example_event));assert r.route(**kwargs(example_event)).reason=='call_budget_exhausted'
        assert r.route(**kwargs(example_event,task_id='another')).action=='inspect'
    assert client.calls==2

def test_remote_requires_spend_bound(cfg,example_event,response):
    client=Client(response);client.is_remote=True
    with router(client,cfg,example_event) as r:assert r.route(**kwargs(example_event)).reason=='unknown_spend_upper_bound'
    assert client.calls==0

def test_cost_overrun_blocks_subsequent_spend(cfg,example_event,response):
    cfg['runtime'].update(input_usd_per_million=1000,output_usd_per_million=0,max_cost_per_task=.01)
    client=Client(response);client.is_remote=True
    with router(client,cfg,example_event) as r:
        assert r.route(**kwargs(example_event,estimated_cost_upper_bound=.001)).action=='stop'
        assert r.route(**kwargs(example_event,estimated_cost_upper_bound=.001)).reason=='cost_budget_exhausted'
    assert client.calls==1

def test_cache_key_scope_ttl_and_permissions(cfg,example_event,response,tmp_path):
    cfg['runtime'].update(cache_ttl_s=60,max_calls_per_task=5);client=Client(response,delay=.002)
    with router(client,cfg,example_event,audit_log=AuditLog(tmp_path/'log.jsonl')) as r:
        args=kwargs(example_event,immutable_state=True,cache_scope='tenant-a:v1')
        assert r.route(**args).action=='inspect';assert r.route(**args).action=='inspect'
        assert client.calls==1
        assert r.route(**{**args,'gate':HostGate(('inspect','stop'),hard_block=True)}).action=='block'
        r.route(**{**args,'cache_scope':'tenant-b:v1'});assert client.calls==2
        for k,(expiry,res,latency) in list(r.cache.items()):r.cache[k]=(0,res,latency)
        r.route(**args);assert client.calls==3
    events=[r['event'] for r in read_jsonl(tmp_path/'log.jsonl')]
    assert any(e.get('cache_hit') for e in events)
    assert all('state' not in e for e in events)

def test_mutable_state_cannot_cache(cfg,example_event,response):
    cfg['runtime']['cache_ttl_s']=60;client=Client(response)
    with router(client,cfg,example_event) as r:
        for _ in range(2):r.route(**kwargs(example_event,cache_scope='x',immutable_state=False))
    assert client.calls==2

def test_shadow_is_nonblocking_and_copies_snapshot(cfg,example_event,response):
    c=cfg['runtime'];c['mode']='shadow';c['timeout_ms']=3000
    release=threading.Event()
    class BlockedClient(Client):
        completed=False
        def evaluate(self,state,questions,model,timeout_ms):
            self.calls+=1
            release.wait(timeout=2)
            self.states.append(copy.deepcopy(state));self.completed=True
            return copy.deepcopy(self.response)
    client=BlockedClient(response);event=copy.deepcopy(example_event)
    with SafeRouter(client,c) as r:
        try:
            result=r.route(**kwargs(event))
            assert result.action=='stop' and not client.completed
            event['state']['objective']='MUTATED AFTER SUBMISSION'
        finally:release.set()
    assert client.states[0]['objective']!='MUTATED AFTER SUBMISSION'

def test_canary_assignment_stable(cfg,example_event,response):
    c=cfg['runtime'];c['mode']='canary';client=Client(response)
    with SafeRouter(client,c,activation=activation(c,example_event)) as r:
        actions=[r.route(**kwargs(example_event,task_id='same-stable-task')).reason for _ in range(3)]
    assert len(set(actions))==1

@pytest.mark.parametrize('bad',['wrong_model','confidence_nan','distribution_sum','label','noul_confidence','missing_question','tokens_negative'])
def test_strict_response_contract(example_event,response,bad):
    if bad=='wrong_model':response['model']='jev-other'
    if bad=='confidence_nan':response['answers']['action']['confidence']=float('nan')
    if bad=='distribution_sum':response['answers']['action']['probabilities']['inspect']=.5
    if bad=='label':response['answers']['action']['choice']='delete_everything'
    if bad=='noul_confidence':response['answers']['sufficient']['confidence']=.99
    if bad=='missing_question':del response['answers']['sufficient']
    if bad=='tokens_negative':response['usage']['input_tokens']=-1
    with pytest.raises(InputError):validate_response(response,example_event['questions'],'jev-1.13.0')

def test_score_is_expected_level_not_boolean_probability():
    q={'s':{'type':'score','instructions':'Rate severity','criteria':['low','medium','high']}}
    response={'model':'jev-1.13.0','answers':{'s':{'type':'score','score':1.3,'confidence':.7,'probabilities':{'0':.1,'1':.5,'2':.4},'legend':{'0':'low','1':'medium','2':'high'}}},'usage':{'input_tokens':20,'output_tokens':0}}
    validate_response(response,q,'jev-1.13.0')
    response['answers']['s']['score']=.8
    with pytest.raises(InputError):validate_response(response,q)

def test_http_egress_consent(monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY','unit-test-dummy')
    with pytest.raises(InputError):TypeSafeHTTPClient()
    with pytest.raises(InputError):TypeSafeHTTPClient(allow_network=True,endpoint='http://api.typesafe.ai/v1/systemone')
    with pytest.raises(InputError):TypeSafeHTTPClient(allow_network=True,endpoint='https://other.example/v1/systemone')
    with pytest.raises(InputError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')

def test_http_contract_mock_only(monkeypatch,example_event,response):
    monkeypatch.setenv('TYPESAFE_API_KEY','unit-test-dummy')
    client=TypeSafeHTTPClient(allow_network=True)
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return json.dumps(response).encode()
    class Opener:
        def open(self,request,timeout):
            assert request.full_url=='https://api.typesafe.ai/v1/systemone'
            assert request.method=='POST'
            payload=json.loads(request.data);assert payload['questions']==example_event['questions']
            assert request.get_header('Authorization')=='Bearer unit-test-dummy'
            return Reply()
    client.opener=Opener()
    assert client.evaluate(example_event['state'],example_event['questions'],'jev-1.13.0',2000)==response

def test_replay_labels_not_downstream_success(example_event,response):
    o=replay_decisions([example_event],Client(response))
    assert o['decision_accuracy_rescues']==1 and 'not identifiable' in o['downstream_task_success']
    del example_event['ground_truth'];o=replay_decisions([example_event],Client(response))
    assert o['labeled_decisions']==0 and o['decision_accuracy_rescues']==0

def test_remote_replay_budget_before_calls(example_event,response):
    client=Client(response);client.is_remote=True
    with pytest.raises(InputError):replay_decisions([example_event],client)
    with pytest.raises(InputError):replay_decisions([example_event]*6,client,cost_upper_bound_per_call=.001)
    assert client.calls==0

def test_audit_redaction_and_tamper_detection(tmp_path):
    log=AuditLog(tmp_path/'events.jsonl');log.append({'api_key':'not-real','message':'Bearer abcdefghi'})
    rows=read_jsonl(tmp_path/'events.jsonl');assert 'not-real' not in str(rows)
    verify_log(rows);rows[0]['event']['message']='changed'
    with pytest.raises(InputError):verify_log(rows)

def test_canary_rollback_rule():
    window=dict(unsafe_actions=1,failure_rate=.01,p95_added_latency_ms=50,mean_added_cost=.001,fallback_rate=.1)
    limits=dict(unsafe_actions=0,failure_rate=.1,p95_added_latency_ms=250,mean_added_cost=.01,fallback_rate=.2)
    assert rollback_check(window,limits)['rollback']
