"""Opt-in exogenous dividend control. Legacy behavior remains the default.

Path indexing is the engine's zero-based PAYMENT round, not dividend_data.csv's
one-based observation round. Stationary single-stock, no factor shocks only.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import random

MODEL_KEYS = ('base_dividend','dividend_variation','dividend_probability','dividend_frequency')

def model_spec(params):
    d=params['DIVIDEND_PARAMS']
    return {k:d[k] for k in MODEL_KEYS}

def payment_rounds(params):
    n=params['NUM_ROUNDS']; f=params['DIVIDEND_PARAMS']['dividend_frequency']
    if type(n) is not int or n < 1 or type(f) is not int or f < 1:
        raise ValueError('NUM_ROUNDS and dividend_frequency must be positive integers')
    return [r for r in range(n) if r % f == 0 and
            not (r == n-1 and not params.get('INFINITE_ROUNDS', False))]

def check_supported(params):
    if params.get('IS_MULTI_STOCK') or params['DIVIDEND_PARAMS'].get('regime_schedule'):
        raise ValueError('Controlled dividends currently require a stationary single-stock scenario')
    if params.get('AGENT_PARAMS', {}).get('shock_structure', {}).get('enabled'):
        raise ValueError('Controlled dividends do not support enabled factor shocks')
    m=model_spec(params)
    if not all(isinstance(m[k], (float,int)) and not isinstance(m[k],bool) and math.isfinite(m[k]) for k in MODEL_KEYS):
        raise ValueError('Dividend model must contain finite numeric parameters')
    if not 0 <= m['dividend_probability'] <= 1 or m['dividend_variation'] < 0:
        raise ValueError('Invalid dividend probability or variation')
    payment_rounds(params)

def generate_path(params, seed):
    check_supported(params)
    if type(seed) is not int: raise ValueError('Dividend seed must be an integer')
    m=model_spec(params);rng=random.Random(seed)
    return {'schema':1, 'round_convention':'zero_based_payment_round',
            'num_rounds':params['NUM_ROUNDS'], 'infinite_rounds':params.get('INFINITE_ROUNDS',False),
            'model':m, 'generation_seed':seed,
            'payments':[{'payment_round_zero_based':r,
                         'dividend_per_share':m['base_dividend'] + (m['dividend_variation'] if
                             rng.random()<m['dividend_probability'] else -m['dividend_variation'])}
                        for r in payment_rounds(params)]}

def validate_path(path, params):
    check_supported(params)
    if path.get('schema')!=1 or path.get('round_convention')!='zero_based_payment_round':
        raise ValueError('Unsupported path schema or round convention')
    if path.get('model') != model_spec(params) or path.get('num_rounds') != params['NUM_ROUNDS'] or path.get('infinite_rounds') != params.get('INFINITE_ROUNDS',False):
        raise ValueError('Path model/horizon does not match scenario')
    payments=path.get('payments',[]);rounds=[p.get('payment_round_zero_based') for p in payments]
    if any(type(r) is not int for r in rounds) or rounds != payment_rounds(params):
        raise ValueError('Payment rounds must match exactly, ordered, without duplicates or missing rounds')
    m=model_spec(params)
    for p in payments:
        v=p.get('dividend_per_share')
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
            raise ValueError('Dividend must be a finite number')
        support=[]
        if m['dividend_probability']>0: support.append(m['base_dividend']+m['dividend_variation'])
        if m['dividend_probability']<1: support.append(m['base_dividend']-m['dividend_variation'])
        if not any(math.isclose(v,s,abs_tol=1e-12) for s in support):
            raise ValueError('Dividend falls outside the specified model support')
    return {p['payment_round_zero_based']:p['dividend_per_share'] for p in payments}

def prepare_control(params):
    control=params.setdefault('DIVIDEND_CONTROL', {'mode':'legacy'})
    mode=control.get('mode','legacy')
    if mode not in ('legacy','independent','replay'): raise ValueError('Unknown dividend control mode')
    if mode=='legacy': return
    check_supported(params)
    for k in ('seed','order_seed'):
        control.setdefault(k,params['RANDOM_SEED'])
        if type(control[k]) is not int: raise ValueError(k+' must be an integer')
    if mode=='replay':
        if control.get('path_file'):
            raw=Path(control['path_file']).read_bytes();path=json.loads(raw)
            control['path_file_sha256']=hashlib.sha256(raw).hexdigest()
        elif 'path' in control: path=control['path']
        else: raise ValueError('Replay requires path_file or embedded path')
        validate_path(path,params)
        control['path']=path
        control['path_content_sha256']=hashlib.sha256(json.dumps(path,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def configure_control(simulation, params):
    c=params.get('DIVIDEND_CONTROL',{});mode=c.get('mode','legacy')
    if mode=='legacy': return
    market=simulation.markets.primary; service=market.dividend_service
    if service is None: raise ValueError('Controlled scenario requires a dividend service')
    service.audit_dividend_mode=mode
    if mode=='independent':
        service.audit_rng=random.Random(c['seed']);service.calculator.rng=service.audit_rng
    else: service.audit_replay=validate_path(c['path'],params)
    market.matching_engine.order_processing_service.rng=random.Random(c['order_seed'])

def save_payment_events(simulation,params,require_complete):
    directory=Path(simulation.run_dir)/'data';directory.mkdir(exist_ok=True)
    rows=[]
    for stock_id,market in simulation.markets.items():
        if market.dividend_service:
            rows.extend(dict(stock_id=stock_id,**e) for e in market.dividend_service.audit_payment_events)
    with (directory/'dividend_payment_events.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['stock_id','payment_round_zero_based','display_round','dividend_per_share','mode','payment_success'])
        w.writeheader();w.writerows(rows)
    c=params.get('DIVIDEND_CONTROL',{});mode=c.get('mode','legacy')
    actual=[r['payment_round_zero_based'] for r in rows]
    check={'mode':mode,'scope':'actual payment events; not lagged observation CSV',
           'payment_count':len(rows),'complete':None,'path_match':None}
    if mode!='legacy':
        check['complete']=actual==payment_rounds(params) and all(r['payment_success'] for r in rows)
        if mode=='replay':
            expected=validate_path(c['path'],params)
            check['path_content_sha256']=c['path_content_sha256']
            check['path_match']=all(r['payment_round_zero_based'] in expected and
                math.isclose(r['dividend_per_share'],expected[r['payment_round_zero_based']],abs_tol=1e-12) for r in rows)
    (Path(simulation.run_dir)/'dividend_control_check.json').write_text(json.dumps(check,indent=2))
    if require_complete and (check['complete'] is False or check['path_match'] is False):
        raise ValueError('Dividend audit failed; see dividend_control_check.json')
