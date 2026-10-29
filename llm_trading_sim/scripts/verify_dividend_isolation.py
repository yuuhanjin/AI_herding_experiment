"""Offline mechanism demonstration, not a GPT experiment or historical attribution."""
from pathlib import Path
import sys,random,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from market.state.services.dividend_service import DividendCalculator
from scenarios import get_scenario

def path(mode,orders_per_round):
    random.seed(42)
    c=DividendCalculator(get_scenario('paper_price_discovery_above').parameters['DIVIDEND_PARAMS'],random.Random(42) if mode=='independent' else None)
    result=[]
    for _ in range(15):
        orders=list(range(orders_per_round));random.shuffle(orders)
        result.append(c.calculate_dividend().total_dividend)
    return result

def main():
    result={'kind':'synthetic offline mechanism check','seed':42,'rounds':15,'orders_per_round':[8,20],
            'caveat':'Demonstrates shared RNG coupling; does not prove the exact cause of historical pair differences.'}
    for mode in ['legacy','independent']:
        a,b=path(mode,8),path(mode,20)
        result[mode]={'path_a':a,'path_b':b,'different_display_rounds':[i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y]}
    assert not result['independent']['different_display_rounds']
    out=Path(__file__).resolve().parents[1]/'audit/rng_isolation_demo.json';out.write_text(json.dumps(result,indent=2))
    print('Legacy differing rounds:',result['legacy']['different_display_rounds'])
    print('Independent differing rounds:',result['independent']['different_display_rounds'])
if __name__=='__main__':main()
