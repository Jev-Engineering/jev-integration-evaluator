"""Explicitly synthetic test setup; never produces a deployment approval."""
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import sys
import time
from jev_integration_evaluator.budget import BudgetCoordinator
from jev_integration_evaluator.integrations.recipes import transform
from jev_integration_evaluator.integrations.probe import SyntheticClient, SyntheticAudit, _fixture_receipt
from scripts.implementation_fixtures import fixture


class FaultClient(SyntheticClient):
    def __init__(self,label):
        super().__init__(label); self.effect=None; self.fault=None
    def evaluate(self,state,questions,model,timeout_ms):
        result=super().evaluate(state,questions,model,timeout_ms)
        if self.effect: self.effect()
        if self.fault=='provider': raise RuntimeError('synthetic provider outage')
        if self.fault=='timeout': time.sleep(.12)
        choice=next(a for a in result['answers'].values() if a['type']=='choice')
        if self.fault=='unknown': choice['choice']='not_registered'
        if self.fault=='distribution': choice['probabilities']={k:1.0 for k in choice['probabilities']}
        if self.fault=='low_confidence': choice['confidence']=0.01
        if self.fault=='low_evidence':
            for a in result['answers'].values():
                if a['type']=='noul':a['noul']=0.0
        if self.fault=='missing_evidence': result['answers'].pop('sufficient',None)
        return result


@contextmanager
def bound_host(tmp_path,pattern='C',*,ledger=None,scope=None,config=None):
    root=tmp_path/'target'; tag=hashlib.sha256(str(tmp_path).encode()).hexdigest()[:14]
    inventory,spec=fixture(root,pattern,tag='t_'+tag)
    if scope:spec['runtime']['canary_scope']=scope
    if config:spec['runtime']['configuration'].update(config)
    derived=transform(root,spec)
    for change in derived['changes']:(root/change['file']).write_text(change['new_content'],encoding='utf-8',newline='')
    module_name=spec['source']['file'][:-3];adapter_name=spec['output']['module']
    sys.path.insert(0,str(root))
    loader=importlib.util.spec_from_file_location(module_name,root/spec['source']['file'])
    module=importlib.util.module_from_spec(loader);sys.modules[module_name]=module;loader.loader.exec_module(module)
    adapter=sys.modules[adapter_name]
    client=FaultClient(spec['verification']['cases'][0]['assessment_label']);audit=SyntheticAudit()
    ledger=ledger or BudgetCoordinator(max_calls_per_task=64,max_cost_per_task=10,max_total_calls=128,
                                       max_total_cost=20,max_in_flight=16,max_tasks=64)
    cfg=copy.deepcopy(spec['runtime']['configuration']);cfg['mode']='active'
    router=adapter.create_router(client,budget_coordinator=ledger,audit_log=audit,runtime_config=cfg)
    router.activation=_fixture_receipt(router,spec)
    adapter.ENABLED=True
    module.__dict__[spec['bindings']['runtime']]=lambda request:router
    request=copy.deepcopy(spec['verification']['cases'][0]['request'])
    def call(request_override=None):
        return module.__dict__[spec['verification']['entry_point']](copy.deepcopy(request if request_override is None else request_override))
    try:yield module,adapter,router,spec,client,call
    finally:
        router.close()
        sys.path.remove(str(root))
        sys.modules.pop(module_name,None);sys.modules.pop(adapter_name,None)
