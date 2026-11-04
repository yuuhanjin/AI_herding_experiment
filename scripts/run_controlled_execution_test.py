"""Explicitly invoked paid pilot; 16 calls maximum, no retries, conservative $1 reservation ceiling."""
import argparse,json,os,sys,time
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--run',action='store_true');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
if not (args.run or args.dry_run):raise SystemExit('Pass --run explicitly to launch the paid pilot.')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'audit'/'controlled_execution_test'/('dry_run' if args.dry_run else 'live')
OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'api_calls.jsonl').exists():raise SystemExit('Existing call ledger: refusing accidental duplicate run.')
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
os.environ['LLM_MAX_RETRIES']='1';os.environ['LLM_REQUEST_TIMEOUT']='60'
os.environ['MPLCONFIGDIR']=str(ROOT/'.cache/matplotlib')
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from scenarios.base import DEFAULT_LLM_BASE_URL,DEFAULT_LLM_MODEL
assert DEFAULT_LLM_BASE_URL=='https://openrouter.ai/api/v1'
assert DEFAULT_LLM_MODEL=='openai/gpt-4o-2024-11-20'
import httpx
if args.dry_run:
    model={'id':DEFAULT_LLM_MODEL,'pricing':{'prompt':'0.0000025','completion':'0.00001'}}
else:
    models=httpx.get(DEFAULT_LLM_BASE_URL+'/models',timeout=20);models.raise_for_status()
    model=next(x for x in models.json()['data'] if x['id']==DEFAULT_LLM_MODEL)
(OUT/'model_metadata.json').write_text(json.dumps(model,indent=2))
pricing=model['pricing'];pr=float(pricing['prompt']);cr=float(pricing['completion'])
from openai.lib._pydantic import to_strict_json_schema
from agents.LLMs.services.llm_services import LLMService
original_init=LLMService.__init__
class PilotStopped(BaseException):pass
ledger=[];reserved=0

def write(row):
    with (OUT/'api_calls.jsonl').open('a') as f:f.write(json.dumps(row,default=str)+'\n')

def init(self):
    original_init(self)
    original_parse=self.client.beta.chat.completions.parse
    def guarded(**kw):
        global reserved
        if len(ledger)>=16:raise PilotStopped('16-call ceiling reached')
        schema=to_strict_json_schema(kw['response_format'])
        quantity=schema['$defs']['OrderSchema']['properties']['quantity']
        assert quantity['maximum']==1000
        assert 'max_order_size = 1000' in kw['messages'][1]['content']
        # One UTF-8 byte per input token plus overhead is a conservative reservation.
        input_bound=len(json.dumps({'messages':kw['messages'],'schema':schema},ensure_ascii=False).encode())+2048
        cost_bound=input_bound*pr+2048*cr
        if reserved+cost_bound>1:raise PilotStopped('Conservative $1 reservation ceiling reached')
        reserved+=cost_bound
        kw['max_tokens']=2048
        idx=len(ledger)+1
        row={'call':idx,'model':kw['model'],'messages':kw['messages'],'schema':schema,
             'max_tokens':2048,'reserved_cost_upper_estimate_usd':cost_bound}
        ledger.append(row);write(row|{'event':'request'})
        print('API_REQUEST',idx,flush=True);start=time.monotonic()
        try:
            if args.dry_run:
                from types import SimpleNamespace as NS
                data=dict(valuation_reasoning='fixture',valuation=28,price_prediction_reasoning='fixture',price_prediction_t=14,price_prediction_t1=14,price_prediction_t2=14,reasoning='fixture',orders=[{'decision':'Buy','quantity':1000,'order_type':'market','price_limit':None}],replace_decision='Add',notes_to_self='',message_reasoning='',post_message='')
                result=NS(id='offline-fixture',model=kw['model'],usage=None,choices=[NS(message=NS(parsed=kw['response_format'](**data),content='{}'),finish_reason='stop')])
            else:
                result=original_parse(**kw)
            if not result.choices or result.choices[0].message.parsed is None:
                raise RuntimeError('Missing parsed response or refusal')
            parsed=result.choices[0].message.parsed
            assert all(1<=o.quantity<=1000 for o in parsed.orders)
            row.update(event='success',id=result.id,response_model=result.model,
                latency_s=time.monotonic()-start,usage=result.usage.model_dump() if result.usage else None,
                response=parsed.model_dump(),finish_reason=result.choices[0].finish_reason)
            write(row);print('API_SUCCESS',idx,'orders',len(parsed.orders),flush=True)
            return result
        except Exception as e:
            # Do not silently replace a failed live call with Hold and continue spending.
            row.update(event='failed',error_type=type(e).__name__,status_code=getattr(e,'status_code',None))
            write(row)
            raise PilotStopped(f'Call {idx} failed: {type(e).__name__}; status {getattr(e,"status_code",None)}') from None
    self.client.beta.chat.completions.parse=guarded
LLMService.__init__=init
import copy
from scenarios import get_scenario
from dividend_controls import generate_path
p=copy.deepcopy(get_scenario('paper_price_discovery_below').parameters);p['NUM_ROUNDS']=2
path=generate_path(p,42)
(OUT/'dividend_path.json').write_text(json.dumps(path,indent=2))
# Dedicated deterministic LP: it neither calls the model nor broadcasts messages.
from agents.deterministic.hold_agent import HoldTrader
from agents.agents_api import TradeDecision
from agents.registry import DETERMINISTIC_AGENTS,_mirror_deterministic_types
class FixedLP(HoldTrader):
    def make_decision(self,market_state,history,round_number):
        return TradeDecision(orders=[],replace_decision='Add',reasoning='Fixed preseeded liquidity; no refresh',valuation=14,valuation_reasoning='fixture',price_prediction_reasoning='fixture',price_prediction_t=14,price_prediction_t1=14,price_prediction_t2=14)
DETERMINISTIC_AGENTS['fixed_test_lp']=FixedLP
_mirror_deterministic_types()
import dividend_controls
original_control=dividend_controls.configure_control
from market.orders.order import Order
from market.orders.trade_execution_service import TradeExecutionService
original_execute=TradeExecutionService.execute_trade
trade_checks=[]
def totals(a):
    return {'cash_total':float(a.cash+a.committed_cash),'shares_total':float(a.positions.get('DEFAULT_STOCK',0)+a.committed_positions.get('DEFAULT_STOCK',0))}
def checked_execute(self,trade):
    buyer=self.agent_repository.get_agent(trade.buyer_id);seller=self.agent_repository.get_agent(trade.seller_id)
    before={'buyer':totals(buyer),'seller':totals(seller)}
    ok=original_execute(self,trade)
    after={'buyer':totals(buyer),'seller':totals(seller)}
    fee=self.position_calculator.get_fee_rate(trade.stock_id)*trade.quantity*trade.price
    import math
    checks={
      'execution_success':bool(ok),
      'buyer_cash':math.isclose(after['buyer']['cash_total']-before['buyer']['cash_total'],-trade.quantity*trade.price-fee,abs_tol=1e-6),
      'seller_cash':math.isclose(after['seller']['cash_total']-before['seller']['cash_total'],trade.quantity*trade.price-fee,abs_tol=1e-6),
      'buyer_shares':after['buyer']['shares_total']-before['buyer']['shares_total']==trade.quantity,
      'seller_shares':after['seller']['shares_total']-before['seller']['shares_total']==-trade.quantity}
    row={'buyer_id':trade.buyer_id,'seller_id':trade.seller_id,'buyer_order_id':trade.buyer_order_id,'seller_order_id':trade.seller_order_id,'quantity':trade.quantity,'price':trade.price,'before':before,'after':after,'checks':checks}
    trade_checks.append(row)
    (OUT/'trade_account_checks.json').write_text(json.dumps(trade_checks,indent=2))
    if not all(checks.values()):raise PilotStopped('Trade/account reconciliation failed')
    return ok
TradeExecutionService.execute_trade=checked_execute
seed_spec=[('buy',500,12.5),('sell',500,13.0),('sell',250,13.01)]
def setup(sim,params):
    original_control(sim,params)
    lp=next(a for a in sim.agent_repository._agents.values() if isinstance(a,FixedLP))
    seeded=[]
    for side,qty,price in seed_spec:
        order=Order(lp.agent_id,'limit',side,qty,0,price=price)
        sim.order_repository.create_order(order)
        ok,reason=sim.order_state_manager.handle_new_order(order,14)
        if not ok:raise PilotStopped('Fixed liquidity seed rejected: '+reason)
        crossing=sim.matching_engine.limit_order_handler.add_non_crossing_orders([order])
        assert not crossing
        sim.agent_repository.record_agent_order(order)
        seeded.append({'order_id':order.order_id,'side':side,'quantity':qty,'price':price})
    (OUT/'fixed_liquidity.json').write_text(json.dumps({'agent_id':lp.agent_id,'orders':seeded,'refresh':False,'scope':'controlled execution test, not replication'},indent=2))
    (OUT/'initial_accounts.json').write_text(json.dumps({str(a.agent_id):totals(a) for a in sim.agent_repository._agents.values()},indent=2))
dividend_controls.configure_control=setup
if args.dry_run:
    import socket
    def blocked(*a,**k):raise RuntimeError('Offline preflight: network prohibited')
    socket.socket.connect=blocked
import run_base_sim as runner
runner.save_plots=lambda *a,**k:None
status={'status':'started','model':DEFAULT_LLM_MODEL,'endpoint':DEFAULT_LLM_BASE_URL,
        'scenario':'controlled_execution_below','initial_price':14,'rounds':2,'gpt_agents':8,'fixed_liquidity_agents':1,'size_mode':'enforced','cap':1000,
        'call_limit':16,'max_completion_tokens':2048,'reservation_ceiling_usd':1}
(OUT/'status.json').write_text(json.dumps(status,indent=2))
try:
    sim=runner.run_scenario('paper_price_discovery_below',param_overrides={
        'NUM_ROUNDS':2,'MODEL_OPEN_AI':DEFAULT_LLM_MODEL,'LLM_MAX_CONCURRENCY':1,
        'AGENT_PARAMS':{'max_order_size':1000,'order_size_mode':'enforced','agent_composition':{'default':2,'optimistic':2,'market_maker':2,'speculator':2,'fixed_test_lp':1}},
        'DIVIDEND_CONTROL':{'mode':'replay','path':path,'seed':42,'order_seed':42}},
        sim_type_override='controlled_execution_20261104_'+('dry' if args.dry_run else 'live'))
    orders=[{'order_id':o.order_id,'agent_id':o.agent_id,'quantity':o.quantity,'side':o.side,
        'type':o.order_type,'price':o.price,'filled':o.filled_quantity,'remaining':o.remaining_quantity,
        'state':o.state.value,'history':o.print_history()} for o in sim.order_repository.orders.values()]
    (OUT/'order_lifecycle.json').write_text(json.dumps(orders,indent=2))
    assert len(ledger)==16 and all(x.get('event')=='success' for x in ledger)
    status.update(status='completed',run_dir=str(sim.run_dir.resolve()),orders=len(orders))
except PilotStopped as e:status.update(status='stopped',reason=str(e))
except Exception as e:
    import traceback
    traceback.print_exc()
    status.update(status='simulation_error',error_type=type(e).__name__)
finally:
    status.update(requests=len(ledger),successful_calls=sum(x.get('event')=='success' for x in ledger),reserved_usd=reserved)
    (OUT/'status.json').write_text(json.dumps(status,indent=2))
    print('PILOT_STATUS',json.dumps(status),flush=True)
