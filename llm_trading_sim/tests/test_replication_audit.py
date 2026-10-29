"""Offline audit regressions; no remote model requests."""
from types import SimpleNamespace as NS
import json
import random
import zipfile
from replication_audit import price_snapshot, write_manifest, safe_params
from market.data_recorder import DataRecorder


def test_quote_change_without_execution_and_missing_side():
    state=random.getstate()
    snap=price_snapshot([],40,50,50)
    assert snap['last_execution_price_this_round'] is None
    assert snap['last_execution_price_to_date'] is None
    assert snap['midpoint_post_match']==45
    assert price_snapshot([],None,50,50)['midpoint_post_match'] is None
    assert random.getstate()==state


def test_execution_order_and_carry_forward():
    snap=price_snapshot([NS(price=16),NS(price=17)],15,18,17)
    assert snap['last_execution_price_this_round']==17
    carry=price_snapshot([],14,19,19,snap['last_execution_price_to_date'])
    assert carry['last_execution_price_this_round'] is None
    assert carry['last_execution_price_to_date']==17
    assert carry['execution_price_is_stale']


def test_recorder_uses_direct_snapshot_not_legacy_quotes(tmp_path):
    snap=price_snapshot([],40,50,50)
    context=NS(current_price=50,fundamental_price=28,public_info={},audit_price_snapshot=snap)
    recorder=DataRecorder(context,None,None,{},tmp_path)
    recorder._record_market_data(0,{'best_bid':1,'best_ask':2},[],0,'now')
    row=recorder.market_data[0]
    assert row['best_bid_post_match']==40
    assert row['best_ask_post_match']==50
    assert row['midpoint_post_match']==45
    assert context.public_info=={}


def test_manifest_records_snapshot_without_credentials(tmp_path):
    params={'MODEL_OPEN_AI':'test-model','API_KEY':'secret-value','nested':{'token':'secret'}}
    write_manifest(tmp_path,params,'started')
    original=json.loads((tmp_path/'run_manifest.json').read_text())
    assert original['parameters']['API_KEY']=='[redacted]'
    with zipfile.ZipFile(tmp_path/'source_snapshot.zip') as z:
        assert 'src/replication_audit.py' in z.namelist()
        assert 'src/llm_config.py' not in z.namelist()
        assert '.env' not in z.namelist()
    write_manifest(tmp_path,params,'completed')
    updated=json.loads((tmp_path/'run_manifest.json').read_text())
    assert original['captured_at_run_start']==updated['captured_at_run_start']
    assert updated['status']=='completed'
