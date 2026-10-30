import copy
import importlib.util
from pathlib import Path

import pytest

NOW = 1780000000000
PATH = Path(__file__).resolve().parents[1] / 's0_smoke' / 'protocol.py'


def state():
    assert PATH.exists(), 'standalone protocol module must exist'
    spec = importlib.util.spec_from_file_location('s0_protocol', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MarketState()


def book(u=2, seq=10):
    return {'topic': 'orderbook.1.BTCUSDT', 'type': 'snapshot', 'ts': NOW,
            'cts': NOW - 1, 'data': {'s': 'BTCUSDT', 'b': [['60000.0', '1']],
            'a': [['60001', '2']], 'u': u, 'seq': seq}}


def trades():
    return {'topic': 'publicTrade.BTCUSDT', 'type': 'snapshot', 'ts': NOW,
            'data': [{'T': NOW-1, 's': 'BTCUSDT', 'S': 'Buy', 'v': '0.010',
                      'p': '60000', 'i': 'trade-one', 'BT': False, 'seq': 10}]}


def test_real_format_and_reconnect_dedup():
    s = state()
    assert s.ingest(book(), NOW)['kind'] == 'book'
    s.ingest(trades(), NOW)
    s.reconnect()
    assert s.summary()['best_bid'] is None
    s.ingest(trades(), NOW)
    x = s.summary()
    assert (x['trade_count'], x['duplicate_trades'], x['buy_volume']) == (1, 1, '0.01')
    assert (x['connections'], x['reconnects']) == (2, 1)


def test_book_duplicate_sequence_reset_and_crossing():
    s = state()
    s.ingest(book(), NOW)
    s.ingest(book(), NOW)
    assert s.summary()['duplicate_books'] == 1
    changed = book()
    changed['data']['b'][0][0] = '59999'
    with pytest.raises(ValueError): s.ingest(changed, NOW)
    s.ingest(book(3, 100), NOW)
    s.ingest(book(1, 1), NOW)
    crossed = book(2, 2)
    crossed['data']['a'][0][0] = '60000'
    with pytest.raises(ValueError): s.ingest(crossed, NOW)
    s.reconnect()
    delta = book(); delta['type'] = 'delta'
    with pytest.raises(ValueError): s.ingest(delta, NOW)


@pytest.mark.parametrize('bad', [True, 1.2, -1, 10**100, NOW-30001, NOW+5001, '1780000000000'])
def test_timestamp_validation(bad):
    s = state(); msg = book(); msg['ts'] = bad
    with pytest.raises(ValueError): s.ingest(msg, NOW)
    assert s.summary()['book_updates'] == 0


@pytest.mark.parametrize('bad', ['1e2', 'NaN', 'Infinity', ' 1', '+1', '01', '.1', '1.', '０.１', '9'*100, '0', '-1', True, 1])
def test_strict_positive_decimal(bad):
    s = state(); msg = trades(); msg['data'][0]['v'] = bad
    with pytest.raises(ValueError): s.ingest(msg, NOW)
    assert s.summary()['trade_count'] == 0


def test_transactional_conflicts_and_batch_bounds():
    s = state(); msg = trades()
    invalid = copy.deepcopy(msg['data'][0]); invalid['i'] = 'two'; invalid['S'] = 'bad'
    msg['data'].append(invalid)
    before = s.summary()
    with pytest.raises(ValueError): s.ingest(msg, NOW)
    assert s.summary() == before
    s.ingest(trades(), NOW)
    changed = trades(); changed['data'][0]['v'] = '2'
    with pytest.raises(ValueError): s.ingest(changed, NOW)
    large = trades(); large['data'] *= 1025
    with pytest.raises(ValueError): s.ingest(large, NOW)


@pytest.mark.parametrize('topic', ['order', 'orderbook.50.BTCUSDT', 'publicTrade.ETHUSDT', ''])
def test_reject_other_topics(topic):
    s = state(); msg = book(); msg['topic'] = topic
    with pytest.raises(ValueError): s.ingest(msg, NOW)


def test_symbol_time_sequence_and_metadata_validation():
    for mutate in [lambda m: m['data'].update(s='ETHUSDT'),
                   lambda m: m.update(cts=NOW+1001),
                   lambda m: m['data'].update(u=True),
                   lambda m: m.update(unexpected='x')]:
        s = state(); msg = book(); mutate(msg)
        with pytest.raises(ValueError): s.ingest(msg, NOW)
    s = state(); s.ingest(book(), NOW)
    with pytest.raises(ValueError): s.ingest(book(3, 9), NOW)
    s = state(); msg = trades(); msg['data'][0]['T'] = NOW+1001
    with pytest.raises(ValueError): s.ingest(msg, NOW)


def test_batch_duplicate_ids_and_decimal_canonicalization():
    s = state(); msg = trades()
    msg['data'].append(copy.deepcopy(msg['data'][0]))
    msg['data'][1]['v'] = '0.01'
    s.ingest(msg, NOW)
    assert s.summary()['trade_count'] == 1
    assert s.summary()['duplicate_trades'] == 1
    assert s.summary()['buy_volume'] == '0.01'


def test_capacity_exhaustion_does_not_evict_or_mutate():
    s = state()
    s._seen = {str(n): ('existing',) for n in range(100000)}
    before = s.summary()
    with pytest.raises(ValueError, match='capacity'): s.ingest(trades(), NOW)
    assert len(s._seen) == 100000
    assert s.summary() == before


def test_trade_sequence_is_not_consecutive_and_repeats_are_allowed():
    s = state()
    for identity, seq in [('one', 5), ('two', 100), ('three', 100)]:
        msg = trades(); msg['data'][0].update(i=identity, seq=seq)
        s.ingest(msg, NOW)
    assert s.summary()['trade_count'] == 3
    msg = trades(); msg['data'][0].update(i='four', seq=99)
    before = s.summary()
    with pytest.raises(ValueError): s.ingest(msg, NOW)
    assert s.summary() == before
    s.reconnect()
    s.ingest(msg, NOW)
    assert s.summary()['trade_count'] == 4


def test_invalid_now_and_trade_fields_do_not_mutate():
    s = state()
    with pytest.raises(ValueError): s.ingest(book(), True)
    for key, value in [('T', True), ('BT', 0), ('seq', True), ('i', '\n'), ('s', 'ETHUSDT')]:
        msg = trades(); msg['data'][0][key] = value
        before = s.summary()
        with pytest.raises(ValueError): s.ingest(msg, NOW)
        assert s.summary() == before


def test_update_one_duplicates_and_reset_timestamp_are_transactional():
    s = state(); s.ingest(book(1, 1), NOW)
    s.ingest(book(1, 1), NOW)
    assert s.summary()['book_updates'] == 1
    assert s.summary()['duplicate_books'] == 1
    changed = book(1, 1); changed['data']['b'][0][0] = '59999'
    before = s.summary()
    with pytest.raises(ValueError): s.ingest(changed, NOW)
    assert s.summary() == before
    s.ingest(book(5, 10), NOW)
    older = book(1, 1); older['ts'] = NOW-1
    before = s.summary()
    with pytest.raises(ValueError): s.ingest(older, NOW)
    assert s.summary() == before
    s.ingest(book(1, 1), NOW)
    assert s.summary()['book_updates'] == 3


def test_trade_batch_timestamp_order_includes_duplicate_rows():
    s = state(); s.ingest(trades(), NOW)
    msg = trades(); new = copy.deepcopy(msg['data'][0])
    new.update(i='newer', T=NOW)
    msg['data'].insert(0, new)
    before = s.summary()
    with pytest.raises(ValueError): s.ingest(msg, NOW)
    assert s.summary() == before
