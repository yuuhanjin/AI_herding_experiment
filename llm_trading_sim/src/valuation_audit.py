"""Figure 7 descriptive audit; one observation per agent-round, not per order.

Limit quotes only: structured logger fills market-order price with a reference
price, which is NOT a chosen limit quote. Missing/nonpositive estimates excluded.
"""
import csv,io,math,statistics
from collections import defaultdict

def numeric(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def median(v): return statistics.median(v) if v else None

def summarize(points):
    vals=[p['valuation'] for p in points if p['valuation'] is not None]
    err=[p['valuation_abs_relative_error'] for p in points if p['valuation_abs_relative_error'] is not None]
    gaps=[p['mean_abs_quote_valuation_gap_over_fundamental'] for p in points if p['mean_abs_quote_valuation_gap_over_fundamental'] is not None]
    near=[p for p in points if p['valuation_abs_relative_error'] is not None and p['valuation_abs_relative_error']<=.1]
    quotable=[p for p in points if p['n_limit_quotes']]
    return {'n_agent_rounds':len(points),'n_valid_valuations':len(vals),'valuation_median':median(vals),
            'valuation_min':min(vals) if vals else None,'valuation_max':max(vals) if vals else None,
            'valuation_population_sd':statistics.pstdev(vals) if vals else None,
            'median_abs_relative_error':median(err),'fraction_within_10pct':len(near)/len(vals) if vals else None,
            'n_agent_rounds_with_limit_quotes':len(quotable),'median_agent_round_quote_gap':median(gaps)}

def analyze_decisions(text,params,market_rows):
    raw=list(csv.DictReader(io.StringIO(text)));groups=defaultdict(list);issues=[]
    for r in raw:
        try:
            rnd=int(r['round'])
            if not 0<=rnd<params['NUM_ROUNDS']: raise ValueError()
        except (KeyError,ValueError): issues.append('Invalid zero-based decision round');continue
        groups[(rnd,r['agent_id'])].append(r)
    points=[];quotes=[]
    previous_prices={int(r['round']):numeric(r['price']) for r in market_rows}
    for (rnd,agent),rr in sorted(groups.items(),key=lambda kv:(kv[0][0],str(kv[0][1]))):
        # The logger repeats exactly the same belief for all orders in one decision.
        # Conflicting estimates/timestamps indicate multiple decision records; do not pick one silently.
        vals={numeric(r.get('valuation')) for r in rr}
        timestamps={r.get('timestamp') for r in rr}
        conflict=len(vals)>1 or len(timestamps)>1
        if conflict: issues.append(f'Conflicting repeated decision: round={rnd}, agent={agent}')
        v=next(iter(vals)) if not conflict else None
        if v is not None and v<=0: v=None
        fv=float(params['FUNDAMENTAL_PRICE'])
        if fv<=0: raise ValueError('Positive fundamental required')
        reference=float(params['INITIAL_PRICE']) if rnd==0 else previous_prices.get(rnd)
        limit_rows=[r for r in rr if str(r.get('order_type','')).lower().split('.')[-1]=='limit'
                    and str(r.get('decision','')).lower() in ('buy','sell')
                    and numeric(r.get('price')) is not None and float(r['price'])>0
                    and numeric(r.get('quantity')) is not None and float(r['quantity'])>0]
        # Repeated orders may be genuine; quote-level export preserves them. Belief statistics do not weight by count.
        gaps=[abs(float(r['price'])-v)/fv for r in limit_rows] if v is not None else []
        p={'round':rnd+1,'decision_round_zero_based':rnd,'agent_id':agent,
           'agent_type':rr[0].get('agent_type_id') or rr[0].get('agent_type'),
           'valuation':v,'fundamental':fv,'valuation_abs_relative_error':abs(v-fv)/fv if v is not None else None,
           'reference_price_before_round':reference,'n_source_rows':len(rr),
           'n_limit_quotes':len(limit_rows),'conflicting_records':conflict,
           'mean_abs_quote_valuation_gap_over_fundamental':statistics.mean(gaps) if gaps else None}
        points.append(p)
        for r in limit_rows:
            quote=float(r['price'])
            quotes.append({'round':rnd+1,'agent_id':agent,'agent_type':p['agent_type'],'side':r['decision'],
                           'quote':quote,'quantity':float(r['quantity']),'valuation':v,
                           'reference_price_before_round':reference,
                           'abs_quote_valuation_gap_over_fundamental':abs(quote-v)/fv if v is not None else None,
                           'closer_to_reference_than_valuation':abs(quote-reference)<abs(quote-v) if reference is not None and v is not None else None})
    composition=params.get('AGENT_PARAMS',{}).get('agent_composition',{})
    expected=sum(composition.values())*params['NUM_ROUNDS'] if composition else None
    if expected is not None and len(points)!=expected: issues.append(f'Expected {expected} agent-rounds, found {len(points)}')
    rounds=[dict(round=r,**summarize([p for p in points if p['round']==r])) for r in range(1,params['NUM_ROUNDS']+1)]
    roles=[dict(agent_type=role,**summarize([p for p in points if p['agent_type']==role])) for role in sorted({p['agent_type'] for p in points})]
    near_quotes=[q for q in quotes if q['valuation'] is not None and abs(q['valuation']-float(params['FUNDAMENTAL_PRICE']))/float(params['FUNDAMENTAL_PRICE'])<=.1]
    return {'source_rows':len(raw),'agent_rounds':points,'limit_quotes':quotes,'round_summary':rounds,
            'role_summary':roles,'overall':summarize(points),'issues':issues,
            'near_fundamental_limit_quote_count':len(near_quotes),
            'near_fundamental_quotes_closer_to_reference':sum(q['closer_to_reference_than_valuation'] is True for q in near_quotes),
            'interpretation':'Descriptive distances, not proof of causal anchoring; reference is previous recorded price, not necessarily last execution.'}
