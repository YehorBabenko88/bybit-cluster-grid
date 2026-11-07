"""Offline real page validation, not ingestion persistence/authority evidence."""
import importlib
import json
import hashlib

import pytest


def api(): return importlib.import_module('grid.market_page_validation')


def identity(symbol='BTCUSDT'):
    return json.dumps(dict(exchange='bybit',category='linear',symbol=symbol,
                           instrument_version='1'),sort_keys=True,separators=(',',':')).encode()


def row(ts='120000'):
    return [ts, '001.2000', '2.0', '1.00', '1.5', '0.0100', '0.0150']


def prepare(rows, **kwargs):
    return api().prepare_kline_page(identity(), rows, '0', '180000', **kwargs)


def test_raw_and_normalized_are_distinct_immutable_images_without_float_rounding():
    rows=[row()]; p=prepare(rows)
    assert json.loads(p.raw_rows_bytes)==rows
    assert json.loads(p.normalized_rows_bytes)==[['120000','1.2','2','1','1.5','0.01','0.015']]
    assert p.raw_rows_sha256==hashlib.sha256(p.raw_rows_bytes).hexdigest()
    rows[0][1]='999'
    assert json.loads(p.raw_rows_bytes)[0][1]=='001.2000'
    assert p.candidate_next_end_ms=='119999'
    assert p.disposition=='PREPARED_UNCOMMITTED'


def test_identical_duplicates_collapse_but_raw_rows_remain():
    p=prepare([row(),row(),row('60000')])
    assert len(json.loads(p.raw_rows_bytes))==3
    assert len(json.loads(p.normalized_rows_bytes))==2
    assert p.duplicate_count=='1'


def test_conflicting_duplicate_never_silently_selects_winner():
    other=row();other[4]='1.6'
    with pytest.raises(api().PageValidationError): prepare([row(),other])


def test_gaps_are_explicit_and_older_unqueried_tail_is_not_declared_complete():
    p=prepare([row('60000')])
    assert p.suspected_gaps==(('120000','180000'),)
    assert p.unobserved_before_ms=='60000'
    assert p.candidate_next_end_ms=='59999'
    assert p.disposition=='PREPARED_UNCOMMITTED'
    p=prepare([row(),row('0')])
    assert p.suspected_gaps==(('60000','120000'),)


def test_empty_page_does_not_advance_cursor_or_claim_complete():
    p=prepare([])
    assert p.candidate_next_end_ms is None
    assert p.suspected_gaps==(('0','180000'),)
    assert p.unobserved_before_ms=='180000'
    assert p.disposition=='PREPARED_UNCOMMITTED'


@pytest.mark.parametrize('rows', [[row('120001')],[row('180000')],
    [row('60000'),row()], [row()[:-1]], [row()+['extra']], [row()]*1001])
def test_timestamp_order_shape_range_and_hard_page_cap(rows):
    with pytest.raises(api().PageValidationError): prepare(rows)


@pytest.mark.parametrize('field,value', [(0,120000),(1,1.2),(1,'1e1'),(1,'NaN'),
    (1,'-1'),(1,'0'),(2,'1.1'),(3,'1.8'),(5,'-0.1'),(6,'x'),(1,'1'*81)])
def test_numeric_types_precision_and_ohlc_invariants(field,value):
    r=row();r[field]=value
    with pytest.raises(api().PageValidationError): prepare([r])


def test_unsupported_category_does_not_reuse_linear_units():
    ident=json.loads(identity());ident['category']='inverse'
    with pytest.raises(api().PageValidationError):
        api().prepare_kline_page(json.dumps(ident,sort_keys=True,separators=(',',':')).encode(),[], '0','180000')


def test_preparer_returns_only_candidates_without_storage_or_authority_fields():
    p=prepare([row()])
    assert not hasattr(p,'committed_cursor')
    assert not hasattr(p,'publication_root_sha256')
    assert not hasattr(p,'complete')


def test_ten_instrument_pages_keep_identity_and_hashes_separate():
    images=[api().prepare_kline_page(identity(f'TEST{i}USDT'),[row()],'0','180000') for i in range(10)]
    assert len({p.instrument_bytes for p in images})==10
    assert all(p.candidate_next_end_ms=='119999' for p in images)
