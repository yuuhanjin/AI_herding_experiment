import copy,json,random
from types import SimpleNamespace as NS
import pytest
from dividend_controls import generate_path,validate_path,prepare_control,payment_rounds,configure_control,save_payment_events
from market.state.services.dividend_service import DividendCalculator,DividendService
from agents.agent_manager.agent_repository import AgentRepository
from market.state.sim_context import SimulationContext
from test_dividend_service import DummyAgent


def params(n=15,infinite=True):
    return {'NUM_ROUNDS':n,'INFINITE_ROUNDS':infinite,'RANDOM_SEED':42,'AGENT_PARAMS':{},
        'DIVIDEND_PARAMS':{'base_dividend':1.4,'dividend_variation':1.,'dividend_probability':.5,'dividend_frequency':1,'destination':'dividend'}}


def service(p):
    context=SimulationContext(num_rounds=p['NUM_ROUNDS'],initial_price=56,fundamental_price=28,redemption_value=None,transaction_cost=0)
    agent=DummyAgent('a',initial_cash=1000,initial_shares=10)
    repo=AgentRepository([agent],logger=None,context=context)
    return DividendService(repo,None,p['DIVIDEND_PARAMS']),agent


def test_legacy_preserves_global_sequence():
    p=params();random.seed(42); expected=[1.4+(1 if random.random()<.5 else -1) for _ in range(15)]
    random.seed(42);c=DividendCalculator(p['DIVIDEND_PARAMS'])
    assert [c.calculate_dividend().total_dividend for _ in range(15)]==expected


def test_independent_stream_is_insulated_from_order_volume():
    p=params();a=DividendCalculator(p['DIVIDEND_PARAMS'],random.Random(42));b=DividendCalculator(p['DIVIDEND_PARAMS'],random.Random(42))
    expected=[a.calculate_dividend().total_dividend for _ in range(15)]
    actual=[]
    for i in range(15):
        orders=list(range(i*13+1));random.shuffle(orders)
        actual.append(b.calculate_dividend().total_dividend)
    assert actual==expected


def test_replay_15_real_account_payments_and_event_export(tmp_path):
    p=params();path=generate_path(p,42);p['DIVIDEND_CONTROL']={'mode':'replay','path':path};prepare_control(p)
    s,a=service(p);market=NS(dividend_service=s,matching_engine=NS(order_processing_service=NS(rng=None)))
    sim=NS(markets=NS(primary=market,items=lambda:[('DEFAULT_STOCK',market)]),run_dir=tmp_path)
    configure_control(sim,p);state=random.getstate()
    for r in range(15): s.process_round_end(r,False)
    assert random.getstate()==state
    assert a.dividend_cash==pytest.approx(10*sum(x['dividend_per_share'] for x in path['payments']))
    assert len(a.payment_history['dividend'])==15
    save_payment_events(sim,p,True)
    check=json.loads((tmp_path/'dividend_control_check.json').read_text())
    assert check['complete'] and check['path_match']
    with pytest.raises(ValueError,match='Duplicate'):s.process_round_end(0,False)


def test_finite_horizon_skips_last_payment():
    p=params(4,False);assert payment_rounds(p)==[0,1,2]
    assert len(generate_path(p,42)['payments'])==3


def test_nonunit_frequency_uses_zero_based_engine_rounds():
    p=params(6);p['DIVIDEND_PARAMS']['dividend_frequency']=2
    assert payment_rounds(p)==[0,2,4]


@pytest.mark.parametrize('mutation',[lambda d:d['payments'].pop(),lambda d:d['payments'].append(d['payments'][0]),lambda d:d.update(round_convention='csv_observation_round'),lambda d:d['payments'][0].update(dividend_per_share=float('nan')),lambda d:d['payments'][0].update(dividend_per_share=99),lambda d:d.update(num_rounds=2),lambda d:d['payments'][0].update(payment_round_zero_based=True)])
def test_invalid_paths_fail_before_run(mutation):
    p=params();d=generate_path(p,42);mutation(d)
    with pytest.raises(ValueError):validate_path(d,p)


def test_invalid_mode_and_unsupported_shocks():
    p=params();p['DIVIDEND_CONTROL']={'mode':'bad'}
    with pytest.raises(ValueError):prepare_control(p)
    p['DIVIDEND_CONTROL']={'mode':'independent'};p['AGENT_PARAMS']={'shock_structure':{'enabled':True}}
    with pytest.raises(ValueError):prepare_control(p)


def test_path_file_is_embedded_and_hashed(tmp_path):
    p=params();f=tmp_path/'path.json';f.write_text(json.dumps(generate_path(p,42)))
    p['DIVIDEND_CONTROL']={'mode':'replay','path_file':str(f)};prepare_control(p)
    c=p['DIVIDEND_CONTROL'];assert len(c['path_file_sha256'])==64 and len(c['path_content_sha256'])==64
    assert len(c['path']['payments'])==15


def test_partial_run_cannot_pass_completeness(tmp_path):
    p=params();p['DIVIDEND_CONTROL']={'mode':'independent'};prepare_control(p)
    s,a=service(p);m=NS(dividend_service=s,matching_engine=NS(order_processing_service=NS(rng=None)))
    sim=NS(markets=NS(primary=m,items=lambda:[('DEFAULT_STOCK',m)]),run_dir=tmp_path);configure_control(sim,p)
    s.process_round_end(0,False)
    with pytest.raises(ValueError):save_payment_events(sim,p,True)
