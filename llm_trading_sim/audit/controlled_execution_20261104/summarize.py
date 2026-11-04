from pathlib import Path
import csv,json,collections,math
p=Path(__file__).resolve().parent/'live'
s=json.loads((p/'status.json').read_text());assert s['status']=='completed',s
run=Path(s['run_dir']);a=[json.loads(x) for x in (p/'api_calls.jsonl').read_text().splitlines()];a=[x for x in a if x['event']=='success']
o=json.loads((p/'order_lifecycle.json').read_text());checks=json.loads((p/'trade_account_checks.json').read_text()) if (p/'trade_account_checks.json').exists() else []
m=list(csv.DictReader((run/'data/market_data.csv').open()))
tf=run/'data/trade_data.csv';t=list(csv.DictReader(tf.open())) if tf.stat().st_size else []
seed=json.loads((p/'fixed_liquidity.json').read_text());lp=seed['agent_id']
summary={'calls':len(a),'provider_cost_usd':round(sum(x['usage']['cost'] for x in a),9),'model':sorted(set(x['response_model'] for x in a)),
 'gpt_proposed_orders':sum(len(x['response']['orders']) for x in a),
 'proposed_quantity_counts':dict(collections.Counter(v['quantity'] for x in a for v in x['response']['orders'])),
 'all_proposals_within_cap':all(1<=v['quantity']<=1000 for x in a for v in x['response']['orders']),
 'trade_count':len(t),'trade_volume':sum(x['quantity'] for x in checks),'account_checks_passed':all(all(x['checks'].values()) for x in checks),
 'gpt_order_states':dict(collections.Counter(x['state'] for x in o if x['agent_id']!=lp)),
 'seed_order_states':dict(collections.Counter(x['state'] for x in o if x['agent_id']==lp)),
 'orders_with_partial_fill_history':[x['order_id'] for x in o if '→ partially_filled' in x['history']],
 'recorded_prices':[float(x['recorded_price']) for x in m],
 'last_execution_per_round':[x['last_execution_price_this_round'] or None for x in m],
 'dividend_check':json.loads((run/'dividend_control_check.json').read_text()),'run_dir':str(run)}
assert len(a)==16 and summary['all_proposals_within_cap']
assert len(checks)==len(t) and summary['account_checks_passed']
assert sum(int(x['num_trades']) for x in m)==len(t)
assert summary['dividend_check']['path_match']
for x in o:
 actual=sum(t['quantity'] for t in checks if x['order_id'] in (t['buyer_order_id'],t['seller_order_id']))
 assert math.isclose(actual,x['filled']), (x,actual)
summary['order_fills_reconcile_to_trades']=True
(p/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
print('TRADES:',json.dumps(t))
print('PARTIAL:',[(x['agent_id'],x['quantity'],x['filled'],x['remaining'],x['state']) for x in o if x['filled']])
