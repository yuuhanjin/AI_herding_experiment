"""Offline synthetic orders exercise the full matching pipeline, bypassing schema.
No LLM behavior or treatment effect is estimated by this fixture.
"""
import sys,os,json,socket,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
def blocked(*a,**k):raise RuntimeError('Offline network block')
socket.socket.connect=blocked
time.sleep=lambda *a:None  # Only skip serial API pacing in this offline process.
from agents.LLMs.services.llm_services import LLMService,LLMResponse
from agents.agents_api import OrderDetails
LLMService.__init__=lambda self:None
def decisions(self,request):
    d=self.get_fallback_decision(request.agent_id,request.enabled_features)
    aid=int(request.agent_id)
    if request.round_number==0:
        # 0/1 valid opposite sides; 2/3 exceed by one; 4/5 oversized MM orders.
        qty={0:1000,1:1000,2:1001,3:1001,4:100000,5:100000,6:1000,7:1000}[aid]
        d['orders']=[OrderDetails(decision='Buy' if aid%2==0 else 'Sell',quantity=qty,
            order_type='limit',price_limit=28)]
    d['reasoning']='Synthetic boundary orders; not GPT decisions'
    return LLMResponse(d,'OFFLINE SYNTHETIC ORDERS')
LLMService.get_decision=decisions
import run_base_sim as runner
runner.save_plots=lambda *a,**k:None
results=[]
for mode in ['legacy','enforced']:
    sim=runner.run_scenario('paper_price_discovery_below',param_overrides={
        'NUM_ROUNDS':2,'INITIAL_PRICE':28,'LLM_MAX_CONCURRENCY':1,
        'AGENT_PARAMS':{'order_size_mode':mode,'max_order_size':1000}},
        sim_type_override='offline_size_synthetic_'+mode)
    rows=[{'order_id':o.order_id,'agent_id':o.agent_id,'side':o.side,'quantity':o.quantity,
           'filled_quantity':o.filled_quantity,'remaining_quantity':o.remaining_quantity,'state':o.state.value,
           'history':o.print_history()} for o in sim.order_repository.orders.values()]
    assert len(rows)==8
    if mode=='enforced':
        rejected=[o for o in rows if o['quantity']>1000]
        assert len(rejected)==4 and all(o['state']=='cancelled' and o['filled_quantity']==0 for o in rejected)
        assert all(o['state']=='filled' for o in rows if o['quantity']==1000)
    else:
        assert any(o['quantity']==100000 and o['filled_quantity']>0 for o in rows)
    results.append({'mode':mode,'run_dir':str(sim.run_dir),'orders':rows})
out=ROOT/'audit/weekly_20261103';out.mkdir(parents=True,exist_ok=True)
(out/'synthetic_order_lifecycle.json').write_text(json.dumps(results,indent=2))
print('Synthetic full-engine checks passed; no API calls.')
