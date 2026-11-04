"""Offline contract tests: parameter -> factory -> prompt/schema -> commitments."""
from types import SimpleNamespace as NS
import copy, logging
import pytest
from pydantic import ValidationError
from order_size_controls import validate_policy, prompt_instruction, rejection_reason
from agents.LLMs.services.schema_features import FeatureRegistry
from agents.base_agent import BaseAgent
from agents.agent_manager.agent_repository import AgentRepository
from agents.agent_manager.services.commitment_services import CommitmentCalculator
from market.state.sim_context import SimulationContext
from market.orders.order import Order, OrderState
from market.orders.order_repository import OrderRepository
from market.orders.order_state_manager import OrderStateManager

class DummyAgent(BaseAgent):
    def make_decision(self,*args): return None

@pytest.mark.parametrize('cap',[0,-1,True,1000.0,None])
def test_invalid_cap(cap):
    with pytest.raises(ValueError): validate_policy(cap,'enforced')

def test_invalid_mode():
    with pytest.raises(ValueError): validate_policy(1000,'typo')

@pytest.mark.parametrize('multi',[False,True])
@pytest.mark.parametrize('cap',[37,1000])
def test_schema_boundaries(multi,cap):
    s=FeatureRegistry.create_order_schema(multi,cap)
    d=dict(decision='Buy',quantity=cap,order_type='limit',price_limit=28)
    if multi:d['stock_id']='TECH_A'
    assert s(**d).quantity==cap
    for q in [0,cap+1,100000]:
        with pytest.raises(ValidationError):s(**(d|{'quantity':q}))
    assert s.model_json_schema()['properties']['quantity']['maximum']==cap

def test_schema_cache_isolation():
    a=FeatureRegistry.get_schema_for_features(set(),False,37)
    b=FeatureRegistry.get_schema_for_features(set(),False,1000)
    c=FeatureRegistry.get_schema_for_features(set())
    assert a is not b and b is not c
    assert 'maximum' not in c.model_json_schema()['$defs']['OrderSchema']['properties']['quantity']

@pytest.mark.parametrize('persona',['default','optimistic','market_maker','speculator'])
def test_factory_parameters_and_type_override(monkeypatch,persona):
    import agents.LLMs.llm_agent as m
    monkeypatch.setattr(m,'LLMService',lambda:None)
    from agents.agent_factory import AgentFactory
    from scenarios import get_scenario
    p=copy.deepcopy(get_scenario('paper_price_discovery_above').parameters)
    f=AgentFactory(initial_price=56,model_open_ai='offline',llm_temperature=0,llm_seed=42,
                   fundamental_info_mode=p['FUNDAMENTAL_INFO_MODE'],system_prompt_overrides={},logger=logging.getLogger())
    p['AGENT_PARAMS'].update(max_order_size=37,order_size_mode='prompt')
    a=f.create_agent(0,persona,p['AGENT_PARAMS'])
    assert (a.max_order_size,a.order_size_mode)==(37,'prompt')
    p['AGENT_PARAMS'].setdefault('type_specific_params',{}).setdefault(persona,{})['max_order_size']=19
    assert f.create_agent(0,persona,p['AGENT_PARAMS']).max_order_size==19

@pytest.mark.parametrize('mode',['legacy','prompt','enforced'])
@pytest.mark.parametrize('side',['buy','sell'])
@pytest.mark.parametrize('kind',['limit','market'])
@pytest.mark.parametrize('qty',[1000,1001,100000])
def test_real_commitment_boundary(mode,side,kind,qty):
    a=DummyAgent(0,initial_cash=1e9,initial_shares=200000,initial_price=28,max_order_size=1000,order_size_mode=mode)
    ctx=SimulationContext(num_rounds=2,initial_price=28,fundamental_price=28,redemption_value=None,transaction_cost=0)
    repo=AgentRepository([a],None,ctx);orders=OrderRepository()
    manager=OrderStateManager(orders,repo,None,None,CommitmentCalculator())
    o=Order(0,kind,side,qty,0,price=28 if kind=='limit' else None)
    orders.create_order(o)
    before=(a.cash,a.shares,a.committed_cash,a.committed_shares)
    ok,msg=manager.handle_new_order(o,28)
    rejected=mode=='enforced' and qty>1000
    assert ok is not rejected
    if rejected:
        assert o.state==OrderState.CANCELLED and 'MAX_ORDER_SIZE_EXCEEDED' in msg
        assert before==(a.cash,a.shares,a.committed_cash,a.committed_shares)
        assert o.quantity==qty and o.current_cash_commitment==o.current_share_commitment==0
    else:assert o.state==OrderState.COMMITTED

def test_forced_liquidation_exemption():
    a=NS(max_order_size=1000,order_size_mode='enforced')
    o=Order(0,'market','sell',100000,0,is_margin_call=True)
    assert rejection_reason(o,a) is None

def test_real_service_passes_bounded_schema_to_api_stub():
    from agents.LLMs.services.llm_services import LLMService,LLMRequest
    service=LLMService.__new__(LLMService)
    captured={}
    def parse(**kw):
        captured.update(kw)
        data=dict(valuation_reasoning='fixture',valuation=28,price_prediction_reasoning='fixture',
                  price_prediction_t=28,price_prediction_t1=28,price_prediction_t2=28,reasoning='fixture',orders=[],replace_decision='Add')
        return NS(choices=[NS(message=NS(content='{}',parsed=kw['response_format'](**data)))],usage=None)
    service.client=NS(beta=NS(chat=NS(completions=NS(parse=parse))))
    service.get_decision(LLMRequest('system',prompt_instruction(37,'enforced'),'offline',0,0,enabled_features=set(),max_order_size=37))
    assert 'max_order_size = 37' in captured['messages'][1]['content']
    assert captured['response_format'].model_json_schema()['$defs']['OrderSchema']['properties']['quantity']['maximum']==37
