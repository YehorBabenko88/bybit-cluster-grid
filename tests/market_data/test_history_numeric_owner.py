"""Literal decimal hand-oracles for canonical historical volume ownership."""
from decimal import Context, Decimal, localcontext
import pytest

from market_data.history_export import export_records
from market_data.history_snapshot import _candle
from market_data.provenance import digest
from test_history_export import fixture


def reseal_volume(records, trust, buy, sell):
    row = records[0]
    previous = row['dataset_fingerprint']
    receipt = trust['receipts'].pop(previous)
    trust['receipt_pins'].pop(previous)
    row['candle'].update(buy_volume=buy, sell_volume=sell)
    revision = digest({key: value for key, value in row.items() if key != 'dataset_fingerprint'})
    row['dataset_fingerprint'] = revision
    receipt['fingerprint'] = revision
    trust['receipts'][revision] = receipt
    trust['receipt_pins'][revision] = digest(receipt)


def test_export_volume_is_canonical_decimal_point_three():
    records, request, trust = fixture(1)
    reseal_volume(records, trust, 0.1, 0.2)
    context = Context(prec=1, Emin=-2, Emax=2)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context) as caller:
        result = export_records(records, request, trust)
        assert not any(caller.flags.values())
    assert result['rows'][0]['volume'] == 0.3


def test_rollup_volume_is_canonical_decimal_point_three():
    rows = [dict(event_start_ms=i * 60000, event_end_ms=(i + 1) * 60000,
                 open=1, high=2, low=1, close=2, volume=volume,
                 available_at_ms=120000, watermark_ms=120000)
            for i, volume in enumerate((0.1, 0.2))]
    assert _candle(rows)['volume'] == 0.3


def test_export_refuses_overflow_and_preserves_tiny_nonzero_volume():
    records, request, trust = fixture(1)
    reseal_volume(records, trust, 1e308, 1e308)
    with pytest.raises(ValueError):
        export_records(records, request, trust)
    records, request, trust = fixture(1)
    reseal_volume(records, trust, 5e-324, 5e-324)
    assert export_records(records, request, trust)['rows'][0]['volume'] == 1e-323
