from decimal import Decimal

import pytest

from grid import terminan_gateway as gateway


def test_candles_preserve_decimal_null_and_epoch_milliseconds(monkeypatch):
    price = Decimal('12345.123456789012345678900')
    row = (Decimal('1795795200000.000000'), price, price, price, price,
           Decimal('0.00000000000000000001'), Decimal('0'), Decimal('-0.01'), 54, None,
           'PARTIAL', ['RECONNECT_GAP'])
    monkeypatch.setattr(gateway, 'query', lambda *args: [row])
    result = gateway.snapshot('/v2/candles', 'BTCUSDT')
    assert result['version'] == 2
    assert result['timeframe'] == '1m'
    assert result['rows'] == [{'t': 1795795200000, 'o': str(price), 'h': str(price),
                               'l': str(price), 'c': str(price), 'buy': '0.00000000000000000001',
                               'sell': '0', 'delta': '-0.01', 'trades': 54, 'poc': None,
                               'quality_status': 'PARTIAL', 'quality_reasons': ['RECONNECT_GAP']}]
    assert result['provenance']['timestamp'] == 'unix_ms_utc'


def test_footprint_preserves_nullable_volume_and_exact_price(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *args: [
        (Decimal('0'), Decimal('1.00000000000000001'), None, Decimal('0'), Decimal('0'), Decimal('0')),
    ])
    assert gateway.snapshot('/v2/footprint')['rows'] == [
        {'t': 0, 'price': '1.00000000000000001', 'buy': None, 'sell': '0', 'delta': '0', 'volume': '0'},
    ]


def test_market_dto_rejects_nonfinite_persisted_numeric(monkeypatch):
    monkeypatch.setattr(gateway, 'query', lambda *args: [
        (Decimal('0'), Decimal('NaN'), Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')),
    ])
    with pytest.raises(ValueError, match='non-finite market numeric'):
        gateway.snapshot('/v2/footprint')


def test_row_cap_marks_partial_bucket_and_empty_snapshot_is_unattested(monkeypatch):
    row = (Decimal('120000'), Decimal('1'), Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'))
    def limited_query(_sql, params):
        assert params == ('BTCUSDT', 2)
        return [row, row]
    monkeypatch.setattr(gateway, 'query', limited_query)
    result = gateway.snapshot('/v2/footprint', limit=1)
    assert len(result['rows']) == 1
    assert result['coverage'] == {'status': 'PARTIAL', 'reason': 'EXCHANGE_COMPLETENESS_UNATTESTED',
                                  'row_limit_reached': True, 'partial_bucket_t': 120000}
    monkeypatch.setattr(gateway, 'query', lambda *args: [])
    empty = gateway.snapshot('/v2/footprint', limit=1)
    assert empty['rows'] == []
    assert empty['coverage']['status'] == 'PARTIAL'
    assert empty['coverage']['partial_bucket_t'] is None
