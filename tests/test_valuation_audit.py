import csv,io
import pytest
from valuation_audit import analyze_decisions


def analyze(rows):
    b=io.StringIO();w=csv.DictWriter(b,fieldnames=['timestamp','round','agent_id','agent_type_id','valuation','order_type','decision','quantity','price']);w.writeheader();w.writerows(rows)
    return analyze_decisions(b.getvalue(),{'NUM_ROUNDS':1,'INITIAL_PRICE':56,'FUNDAMENTAL_PRICE':28,'AGENT_PARAMS':{'agent_composition':{'default':1}}},[])


def row(**kw):
    return dict(timestamp='now',round=0,agent_id='0',agent_type_id='default',valuation=28,order_type='OrderType.LIMIT',decision='Buy',quantity=100,price=50,**kw)


def test_multiple_orders_count_as_one_belief_and_exclude_market_reference_price():
    a=row();b=dict(a,price=54);c=dict(a,order_type='OrderType.MARKET',price=56)
    v=analyze([a,b,c]);assert len(v['agent_rounds'])==1 and len(v['limit_quotes'])==2
    assert v['overall']['valuation_median']==28
    assert v['agent_rounds'][0]['round']==1
    assert v['overall']['median_agent_round_quote_gap']==pytest.approx(24/28)


def test_zero_missing_estimate_not_treated_as_true_valuation():
    v=analyze([dict(row(),valuation=0)])
    assert v['overall']['n_valid_valuations']==0
    assert v['overall']['valuation_median'] is None


def test_conflicting_repeated_decisions_flagged():
    v=analyze([row(),dict(row(),valuation=96)])
    assert v['issues'] and v['agent_rounds'][0]['valuation'] is None


def test_hold_has_belief_but_no_quote():
    v=analyze([dict(row(),decision='Hold',order_type='none',quantity=0)])
    assert v['overall']['n_valid_valuations']==1 and v['limit_quotes']==[]
