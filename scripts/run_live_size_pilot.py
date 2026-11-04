"""Explicitly invoked paid pilot; 16 calls maximum, no retries, conservative $1 reservation ceiling."""
import argparse,json,os,sys,time
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--run',action='store_true');args=ap.parse_args()
if not args.run:raise SystemExit('Pass --run explicitly to launch the paid pilot.')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'audit'/'live_size_pilot'
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
import run_base_sim as runner
runner.save_plots=lambda *a,**k:None
status={'status':'started','model':DEFAULT_LLM_MODEL,'endpoint':DEFAULT_LLM_BASE_URL,
        'scenario':'below','initial_price':14,'rounds':2,'agents':8,'size_mode':'enforced','cap':1000,
        'call_limit':16,'max_completion_tokens':2048,'reservation_ceiling_usd':1}
(OUT/'status.json').write_text(json.dumps(status,indent=2))
try:
    sim=runner.run_scenario('paper_price_discovery_below',param_overrides={
        'NUM_ROUNDS':2,'MODEL_OPEN_AI':DEFAULT_LLM_MODEL,'LLM_MAX_CONCURRENCY':1,
        'AGENT_PARAMS':{'max_order_size':1000,'order_size_mode':'enforced'},
        'DIVIDEND_CONTROL':{'mode':'replay','path':path,'seed':42,'order_seed':42}},
        sim_type_override='live_gpt_size_enforced_20261104')
    orders=[{'order_id':o.order_id,'agent_id':o.agent_id,'quantity':o.quantity,'side':o.side,
        'type':o.order_type,'price':o.price,'filled':o.filled_quantity,'remaining':o.remaining_quantity,
        'state':o.state.value,'history':o.print_history()} for o in sim.order_repository.orders.values()]
    (OUT/'order_lifecycle.json').write_text(json.dumps(orders,indent=2))
    assert len(ledger)==16 and all(x.get('event')=='success' for x in ledger)
    status.update(status='completed',run_dir=str(sim.run_dir.resolve()),orders=len(orders))
except PilotStopped as e:status.update(status='stopped',reason=str(e))
except Exception as e:status.update(status='simulation_error',error_type=type(e).__name__)
finally:
    status.update(requests=len(ledger),successful_calls=sum(x.get('event')=='success' for x in ledger),reserved_usd=reserved)
    (OUT/'status.json').write_text(json.dumps(status,indent=2))
    print('PILOT_STATUS',json.dumps(status),flush=True)
