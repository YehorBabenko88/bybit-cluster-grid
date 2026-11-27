"""Offline tests for a descriptive ONLY Grid adapter; no Bybit, DB or trading."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from grid.qualified_ohlcv import descriptive_snapshot, DescriptiveReadError

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def row(minute, value='1', source='BYBIT_REST', turnover='2'):
    return (_EPOCH + timedelta(milliseconds=minute), Decimal(value),
            Decimal('2'), Decimal('0.5'), Decimal(value),
            Decimal('0.000000000000000001'),
            Decimal(turnover) if turnover is not None else None, source)


class ReadSpy:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        return self.records


class QualifiedOhlcvDescriptiveTests(unittest.TestCase):
    def test_full_five_minutes_is_partial_never_trusted(self):
        spy = ReadSpy([row(t) for t in range(0, 300_000, 60_000)])
        got = descriptive_snapshot('BTCUSDT', 0, 300_000, 600_000, reader=spy)
        self.assertEqual(got['status'], 'PARTIAL')
        self.assertEqual(got['coverage']['missing_minutes'], 0)
        self.assertEqual(got['rows'][0]['volume'], '0.000000000000000001')
        self.assertEqual(got['provenance']['availability_at_decision'], 'UNATTESTED')
        self.assertIsNone(got['provenance']['independent_receipt'])
        self.assertFalse(got['causal_research_admitted'])
        self.assertFalse(got['execution_authority'])
        self.assertFalse(got['trading_authorized'])
        self.assertEqual(len(spy.calls), 1)
        self.assertIn('FROM ohlcv_1m', spy.calls[0][0])
        self.assertNotIn('candles_1m', spy.calls[0][0])
        self.assertEqual(spy.calls[0][1][-1], 6)

    def test_missing_head_and_tail_detected_from_requested_bounds(self):
        got = descriptive_snapshot('BTCUSDT', 0, 300_000, 600_000,
                                   reader=ReadSpy([row(60_000),row(120_000),row(180_000)]))
        self.assertEqual(got['status'], 'GAP')
        self.assertEqual(got['coverage']['missing_minutes'], 2)
        self.assertEqual([(g['start_ms'],g['end_ms']) for g in got['coverage']['gaps']],
                         [(0,60_000),(240_000,300_000)])

    def test_internal_gap_is_not_silently_filled(self):
        got = descriptive_snapshot('BTCUSDT', 0, 300_000, 600_000,
                                   reader=ReadSpy([row(0),row(60_000),row(180_000),row(240_000)]))
        self.assertEqual(got['coverage']['gaps'][0]['start_ms'], 120_000)
        self.assertEqual(got['coverage']['gaps'][0]['end_ms'], 180_000)
        self.assertFalse(got['paper_admitted'])

    def test_empty_returns_unavailable_not_zero_candles(self):
        got = descriptive_snapshot('BTCUSDT', 0, 120_000, 120_000,
                                   reader=ReadSpy([]))
        self.assertEqual(got['status'], 'UNAVAILABLE')
        self.assertEqual(got['coverage']['missing_minutes'], 2)
        self.assertEqual(got['rows'], [])

    def test_duplicate_revision_refuses_without_partial_result(self):
        with self.assertRaisesRegex(DescriptiveReadError, 'DUPLICATE'):
            descriptive_snapshot('BTCUSDT', 0, 120_000, 120_000,
                                 reader=ReadSpy([row(0),row(0)]))

    def test_row_limit_overrun_refuses(self):
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_COUNT_AMBIGUOUS'):
            descriptive_snapshot('BTCUSDT', 0, 60_000, 60_000,
                                 reader=ReadSpy([row(0),row(0)]))

    def test_mixed_declared_source_does_not_authenticate_either(self):
        got = descriptive_snapshot('BTCUSDT', 0, 120_000, 120_000,
                                   reader=ReadSpy([row(0),row(60_000,source='OTHER')]))
        self.assertEqual(got['provenance']['source_declarations'], ['BYBIT_REST','OTHER'])
        self.assertEqual(got['provenance']['source_authenticity'], 'UNATTESTED')

    def test_unknown_turnover_is_null_not_zero(self):
        got = descriptive_snapshot('BTCUSDT', 0, 60_000, 60_000,
                                   reader=ReadSpy([row(0,turnover=None)]))
        self.assertIsNone(got['rows'][0]['turnover'])

    def test_invalid_numeric_or_float_refuses(self):
        invalid = list(row(0)); invalid[1] = float('nan')
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_DECIMAL_REQUIRED'):
            descriptive_snapshot('BTCUSDT',0,60_000,60_000,reader=ReadSpy([tuple(invalid)]))
        invalid[1] = Decimal('Infinity')
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_DECIMAL_REQUIRED'):
            descriptive_snapshot('BTCUSDT',0,60_000,60_000,reader=ReadSpy([tuple(invalid)]))

    def test_invalid_query_rejected_before_reader_invoked(self):
        for args in [('btcUSDT',0,60_000,60_000),
                     ('BTCUSDT',True,60_000,60_000),
                     ('BTCUSDT',0,60_001,60_001),
                     ('BTCUSDT',0,120_000,60_000),
                     ('BTCUSDT',0,60_000,0)]:
            spy = ReadSpy([row(0)])
            with self.assertRaises(DescriptiveReadError):
                descriptive_snapshot(*args,reader=spy)
            self.assertEqual(spy.calls, [])

    def test_outside_window_timestamp_refuses(self):
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_TIME_OUTSIDE_SELECTION'):
            descriptive_snapshot('BTCUSDT',60_000,120_000,120_000,
                                 reader=ReadSpy([row(0)]))

    def test_out_of_order_rows_refuse(self):
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_ORDER_REQUIRED'):
            descriptive_snapshot('BTCUSDT',0,120_000,120_000,
                                 reader=ReadSpy([row(60_000),row(0)]))

    def test_naive_datetime_refuses(self):
        invalid=list(row(0));invalid[0]=datetime(1970,1,1)
        with self.assertRaisesRegex(DescriptiveReadError, 'ROW_UTC_TIMESTAMP_REQUIRED'):
            descriptive_snapshot('BTCUSDT',0,60_000,60_000,reader=ReadSpy([tuple(invalid)]))


if __name__ == '__main__':
    unittest.main()
