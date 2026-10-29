"""Generate a path offline. Does not construct a simulation or call a model."""
from pathlib import Path
import argparse,sys,json,copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from dividend_controls import generate_path
from scenarios import get_scenario

def main():
    p=argparse.ArgumentParser();p.add_argument('--scenario',default='paper_price_discovery_above');p.add_argument('--seed',type=int,default=42);p.add_argument('--output',required=True);p.add_argument('--rounds',type=int)
    a=p.parse_args();path=Path(a.output)
    if path.exists(): raise SystemExit('Refusing to overwrite an existing path; choose another output.')
    params=copy.deepcopy(get_scenario(a.scenario).parameters)
    if a.rounds is not None: params['NUM_ROUNDS']=a.rounds
    data=generate_path(params,a.seed)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2))
    print(f'Offline path saved: {path} ({len(data["payments"])} payment rounds). No API calls.')
if __name__=='__main__': main()
