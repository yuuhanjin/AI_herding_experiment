"""No-API prompt audit and controlled-path integration checks.

Run with .venv/bin/python scripts/audit_order_size.py. Socket connections are
blocked; model decisions are deterministic Hold fixtures, NOT GPT results.
"""
import copy,json,os,re,socket,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.chdir(ROOT)
OUT=ROOT/'audit/weekly_20261103'
OUT.mkdir(parents=True,exist_ok=True)
def blocked(*a,**k):raise RuntimeError('Network blocked: offline audit')
socket.socket.connect=blocked
import time
time.sleep=lambda *a:None  # Skip API pacing only inside this network-blocked audit process.
from agents.LLMs.services.llm_services import LLMService,LLMResponse
from agents.LLMs.services.schema_features import FeatureRegistry
from scenarios import get_scenario
from dividend_controls import generate_path
LLMService.__init__=lambda self:None
records=[]
cell={}
def capture(self,request):
    schema=FeatureRegistry.get_schema_for_features(request.enabled_features,request.is_multi_stock,request.max_order_size).model_json_schema()
    records.append(dict(cell,agent_id=request.agent_id,round=request.round_number,
        system_prompt=request.system_prompt,user_prompt=request.user_prompt,
        schema_quantity=schema['$defs']['OrderSchema']['properties']['quantity']))
    d=self.get_fallback_decision(request.agent_id,request.enabled_features)
    d['reasoning']='Offline Hold fixture; not a model prediction'
    return LLMResponse(d,'OFFLINE HOLD FIXTURE')
LLMService.get_decision=capture
import run_base_sim as runner
runner.save_plots=lambda *a,**k:None
checks=[]
for side in ['above','below']:
    for mode in ['legacy','prompt','enforced']:
        for cap in [1000,37]:
            cell.clear();cell.update(side=side,mode=mode,cap=cap,kind='prompt_capture')
            start=len(records)
            sim=runner.run_scenario('paper_price_discovery_'+side,
                param_overrides={'NUM_ROUNDS':2,'LLM_MAX_CONCURRENCY':1,
                    'AGENT_PARAMS':{'max_order_size':cap,'order_size_mode':mode}},
                sim_type_override=f'offline_size_{side}_{mode}_{cap}')
            subset=records[start:]
            assert len(subset)==16, 'Missing requests; inspect decision errors'
            for rec in subset:
                assert (f'max_order_size = {cap}' in rec['user_prompt']) == (mode!='legacy')
                assert rec['schema_quantity'].get('maximum') == (cap if mode=='enforced' else None)
            checks.append(dict(cell,requests=len(subset),passed=True,run_dir=str(sim.run_dir)))
# Full 15-round replay verifies controls in the actual simulation, with Hold fixtures.
p=copy.deepcopy(get_scenario('paper_price_discovery_above').parameters)
path=generate_path(p,42)
(OUT/'dividend_path_seed42.json').write_text(json.dumps(path,indent=2))
for side in ['above','below']:
    cell.clear();cell.update(side=side,mode='enforced',cap=1000,kind='15_round_replay')
    sim=runner.run_scenario('paper_price_discovery_'+side,
        param_overrides={'LLM_MAX_CONCURRENCY':1,'AGENT_PARAMS':{'max_order_size':1000,'order_size_mode':'enforced'},
            'DIVIDEND_CONTROL':{'mode':'replay','path':path,'seed':42,'order_seed':42}},
        sim_type_override=f'offline_size_replay15_{side}')
    check=json.loads((sim.run_dir/'dividend_control_check.json').read_text())
    assert check['complete'] and check['path_match']
    checks.append(dict(cell,passed=True,run_dir=str(sim.run_dir),dividend_check=check))
(OUT/'rendered_requests.json').write_text(json.dumps(records,indent=2))
(OUT/'checks.json').write_text(json.dumps({'offline':True,'api_calls':0,'checks':checks,'requests':len(records)},indent=2))
# Describe the future matched batch without launching it.
batch=[]
for seed in [42,43,44]:
    dp=generate_path(p,seed)
    for side in ['above','below']:
        for mode in ['legacy','prompt','enforced']:
            batch.append({'label':f'{side}_{seed}_{mode}','scenario':'paper_price_discovery_'+side,
                'param_overrides':{'NUM_ROUNDS':15,'MODEL_OPEN_AI':'openai/gpt-4o-2024-11-20',
                    'LLM_TEMPERATURE':0,'LLM_SEED':42,'LLM_MAX_CONCURRENCY':1,
                    'AGENT_PARAMS':{'max_order_size':1000,'order_size_mode':mode},
                    'DIVIDEND_CONTROL':{'mode':'replay','path':dp,'seed':seed,'order_seed':seed}}})
(OUT/'planned_matched_batch_NOT_RUN.json').write_text(json.dumps({'status':'NOT RUN; requires API budget approval','cells':batch},indent=2))
print('AUDIT COMPLETE:',len(records),'captured requests; zero API calls;',OUT)
