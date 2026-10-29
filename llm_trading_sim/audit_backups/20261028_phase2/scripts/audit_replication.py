"""Offline audit: python scripts/audit_replication.py [--archive FILE.zip ...]."""
from pathlib import Path
import argparse, csv, io, json, zipfile, hashlib, datetime

ROOT = Path(__file__).resolve().parents[1]

def number(v):
    try:
        n = float(v)
        return n if __import__('math').isfinite(n) else None
    except (TypeError, ValueError):
        return None

def audit_run(name, read, source):
    params = json.loads(read('parameters.json'))
    markets = list(csv.DictReader(io.StringIO(read('data/market_data.csv'))))
    trades = list(csv.DictReader(io.StringIO(read('data/trade_data.csv'))))
    if any(m.get('stock_id', 'DEFAULT_STOCK') != 'DEFAULT_STOCK' for m in markets):
        raise ValueError('This report supports the single-stock replication scenarios only')
    by_round = {}
    for t in trades:
        by_round.setdefault(int(t['round']), []).append(t)
    rows = []; previous = None
    for m in markets:
        r = int(m['round']); ts = by_round.get(r, [])
        last = number(ts[-1]['price']) if ts else None
        if last is not None: previous = last
        verified = m.get('quote_snapshot_phase') == 'post_matching'
        bid = number(m.get('best_bid_post_match')) if verified else None
        ask = number(m.get('best_ask_post_match')) if verified else None
        rows.append({'round': r, 'recorded_price': number(m['price']),
                     'fundamental_price': number(m['fundamental_price']),
                     'last_execution_price_this_round': last,
                     'last_execution_price_to_date': previous,
                     'execution_price_is_stale': not ts and previous is not None,
                     'best_bid_post_match': bid, 'best_ask_post_match': ask,
                     'midpoint_post_match': (bid + ask)/2 if bid is not None and ask is not None else None,
                     'quote_timing_verified': verified,
                     'legacy_best_bid_unverified': number(m.get('best_bid')),
                     'legacy_best_ask_unverified': number(m.get('best_ask')),
                     'trade_count': len(ts), 'volume': sum(float(t['quantity']) for t in ts)})
    issues = []
    for m, row in zip(markets, rows):
        if number(m.get('num_trades')) != row['trade_count']: issues.append(f"round {row['round']}: trade count mismatch")
        if number(m.get('total_volume')) is None or abs(float(m['total_volume'])-row['volume'])>1e-6: issues.append(f"round {row['round']}: volume mismatch")
    try:
        divs = list(csv.DictReader(io.StringIO(read('data/dividend_data.csv'))))
        dividends = {d['round']: number(d['last_paid_dividend']) for d in divs}
    except (FileNotFoundError, KeyError): dividends = None
    try: manifest = json.loads(read('run_manifest.json')); provenance = manifest.get('provenance_kind', 'unknown')
    except (FileNotFoundError, KeyError): provenance = 'retrospective_only'
    selected = {k: params.get(k) for k in ['INITIAL_PRICE','FUNDAMENTAL_PRICE','NUM_ROUNDS','MODEL_OPEN_AI','LLM_SEED','RANDOM_SEED','LLM_TEMPERATURE','LLM_MAX_CONCURRENCY','SYSTEM_PROMPT_OVERRIDES','INFINITE_ROUNDS','FUNDAMENTAL_INFO_MODE','AGENT_PARAMS']}
    return {'id': name, 'source': source, 'parameters': selected, 'rows': rows,
            'dividends': dividends, 'provenance': provenance, 'issues': issues,
            'trade_count': len(trades), 'volume': sum(float(t['quantity']) for t in trades),
            'input_sha256': {f: hashlib.sha256(read(f).encode()).hexdigest() for f in
                             ['parameters.json','data/market_data.csv','data/trade_data.csv']}}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--archive', action='append', default=[])
    args = parser.parse_args(); out = ROOT / 'audit/dashboard'; out.mkdir(parents=True, exist_ok=True)
    runs=[]; errors=[]
    for p in sorted((ROOT/'logs').glob('replication_*/*/parameters.json')):
        if 'pilot' in p.parts[-3]: continue
        root=p.parent
        try: runs.append(audit_run(root.name, lambda f: (root/f).read_text(), str(root)))
        except Exception as e: errors.append({'source':str(root),'error':str(e)})
    for archive in args.archive:
        try:
            with zipfile.ZipFile(archive) as z:
                names=[n for n in z.namelist() if not n.startswith('__MACOSX')]
                def read(f):
                    matches=[n for n in names if n==f or n.endswith('/'+f)]
                    if len(matches)!=1: raise KeyError(f)
                    return z.read(matches[0]).decode()
                runs.append(audit_run(Path(archive).stem,read,str(Path(archive).resolve())))
        except Exception as e: errors.append({'source':archive,'error':str(e)})
    pairs=[]
    for a,b in [('20261014_234547','20261015_000510'),('20261014_234649','20261015_000618')]:
        aa=next((r for r in runs if r['id']==a),None);bb=next((r for r in runs if r['id']==b),None)
        if aa and bb:
            x,y=aa['dividends'],bb['dividends']
            different=None if x is None or y is None else sorted([r for r in set(x)|set(y) if x.get(r)!=y.get(r)],key=int)
            pairs.append({'baseline':a,'treatment':b,'different_dividend_rounds':different,
                          'changed_parameters':[k for k in aa['parameters'] if aa['parameters'][k]!=bb['parameters'][k]]})
    result={'generated_at':datetime.datetime.now().astimezone().isoformat(),'runs':runs,'pairs':pairs,'errors':errors,
            'scope':'Offline reconstruction; trade CSV row order used for last execution within each round. Legacy quote timing unverified.'}
    for run in runs:
        with (out/(run['id']+'_prices.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(run['rows'][0]));w.writeheader();w.writerows(run['rows'])
    (out/'audit_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    template=(ROOT/'scripts/audit_dashboard.html').read_text()
    (out/'index.html').write_text(template.replace('__AUDIT_DATA__',json.dumps(result,ensure_ascii=False).replace('<','\\u003c')))
    print(f'Audited {len(runs)} runs; {len(errors)} input errors. Dashboard: {out / "index.html"}')
    if errors: raise SystemExit(1)

if __name__=='__main__': main()
