"""In-process, socket-free tests for the opt-in Grid descriptive OHLCV route."""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from grid import terminan_gateway as gateway


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
BASE = '/v1/ohlcv/descriptive?symbol=BTCUSDT&start_ms=0&end_ms=120000&as_of_ms=120000'


def record(ms, value='0.000000000000000001', turnover=None):
    return (_EPOCH + timedelta(milliseconds=ms), Decimal(value),
            Decimal('2'), Decimal('0.5'), Decimal('1.5'), Decimal('1'),
            None if turnover is None else Decimal(turnover), 'BYBIT_REST')


def invoke(path, *, records=(), error=None):
    # Neither HTTP sockets nor PostgreSQL are started. Existing Handler is called
    # with its response methods replaced by in-memory recording callbacks.
    calls = []

    def reader(sql, params=()):
        calls.append((sql, params))
        if error is not None:
            raise error
        return list(records)

    h = object.__new__(gateway.Handler)
    h.path = path
    h.wfile = io.BytesIO()
    statuses = []
    headers = []
    h.send_response = statuses.append
    h.send_header = lambda k, v: headers.append((k, v))
    h.end_headers = lambda: None
    with patch.object(gateway, 'query', reader):
        h.do_GET()
    body = h.wfile.getvalue()
    return statuses[0], dict(headers), json.loads(body), body, calls


class DescriptiveHTTPTests(unittest.TestCase):
    def test_complete_rows_still_partial_unattested(self):
        code, headers, data, body, calls = invoke(BASE, records=[record(0), record(60000)])
        self.assertEqual(code, 200)
        self.assertEqual(headers['Content-Length'], str(len(body)))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(data['schema'], 'grid.ohlcv_1m.descriptive.v1')
        self.assertEqual(data['status'], 'PARTIAL')
        self.assertEqual(data['rows'][0]['open'], '0.000000000000000001')
        self.assertIsNone(data['rows'][0]['turnover'])
        self.assertEqual(data['provenance']['source_authenticity'], 'UNATTESTED')
        self.assertEqual(data['provenance']['availability_at_decision'], 'UNATTESTED')
        self.assertFalse(data['causal_research_admitted'])
        self.assertFalse(data['execution_authority'])
        self.assertFalse(data['trading_authorized'])
        self.assertEqual(len(calls), 1)
        self.assertIn('FROM ohlcv_1m', calls[0][0])

    def test_missing_row_gap_and_no_filled_zero(self):
        code, _, data, _, _ = invoke(BASE, records=[record(0)])
        self.assertEqual(code, 200)
        self.assertEqual(data['status'], 'GAP')
        self.assertEqual(data['coverage']['gaps'][0]['start_ms'], 60000)
        self.assertEqual(data['coverage']['gaps'][0]['end_ms'], 120000)
        self.assertEqual(len(data['rows']), 1)

    def test_empty_history_unavailable(self):
        code, _, data, _, _ = invoke(BASE)
        self.assertEqual(code, 200)
        self.assertEqual(data['status'], 'UNAVAILABLE')
        self.assertEqual(data['coverage']['missing_minutes'], 2)

    def test_malformed_or_unknown_or_duplicate_parameters_fail_closed_before_reader(self):
        bad = [
            BASE + '&symbol=BTCUSDT', BASE + '&unexpected=1',
            BASE.replace('symbol=BTCUSDT', 'symbol='),
            BASE.replace('symbol=BTCUSDT', 'symbol=btcUSDT'),
            BASE.replace('start_ms=0', 'start_ms=-1'),
            BASE.replace('start_ms=0', 'start_ms=+0'),
            BASE.replace('start_ms=0', 'start_ms=00'),
            BASE.replace('end_ms=120000', 'end_ms=120001'),
            BASE.replace('as_of_ms=120000', 'as_of_ms=60000'),
            BASE.replace('as_of_ms=120000', 'as_of_ms=9007199254740992'),
            BASE.replace('start_ms=0&', ''),
            BASE.replace('&end_ms=120000', ''),
            BASE.replace('&as_of_ms=120000', ''),
            BASE.replace('&', '&&', 1),
            BASE + '&x=' + ('a' * 600),
        ]
        for path in bad:
            with self.subTest(path=path[:80]):
                code, headers, data, body, calls = invoke(path)
                self.assertEqual(code, 400)
                self.assertEqual(data, {'error': 'invalid descriptive request'})
                self.assertEqual(headers['Content-Length'], str(len(body)))
                self.assertEqual(calls, [])

    def test_persisted_duplicate_is_503_without_source_details(self):
        code, headers, data, _, calls = invoke(BASE, records=[record(0), record(0)])
        self.assertEqual(code, 503)
        self.assertEqual(data, {'error': 'source unavailable'})
        self.assertEqual(len(calls), 1)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_corrupt_decimal_is_503_not_leaked(self):
        rows = [list(record(0))]
        rows[0][1] = Decimal('NaN')
        code, _, data, _, _ = invoke(BASE, records=[tuple(rows[0])])
        self.assertEqual(code, 503)
        self.assertEqual(data, {'error': 'source unavailable'})

    def test_sql_connection_error_is_503_not_leaked(self):
        code, _, data, _, _ = invoke(BASE, error=RuntimeError('private db password'))
        self.assertEqual(code, 503)
        self.assertNotIn('private', json.dumps(data))

    def test_gateway_response_byte_budget(self):
        with patch.object(gateway, 'MAX_RESPONSE_BYTES', 100):
            code, _, data, _, _ = invoke(BASE, records=[record(0)])
        self.assertEqual(code, 503)
        self.assertEqual(data, {'error': 'source unavailable'})

    def test_v1_candles_alias_same_v2_bytes(self):
        candle = (Decimal('120000'), Decimal('1.000000000000000001'),
                  Decimal('2'), Decimal('0'), Decimal('1'),
                  Decimal('0.1'), Decimal('0.2'), Decimal('-0.1'), 4, None,
                  'PARTIAL', ['SOURCE_GAP'])
        status1, _, obj1, body1, _ = invoke('/v1/candles?symbol=BTCUSDT', records=[candle])
        status2, _, obj2, body2, _ = invoke('/v2/candles?symbol=BTCUSDT', records=[candle])
        self.assertEqual((status1, status2), (200, 200))
        self.assertEqual(obj1, obj2)
        self.assertEqual(body1, body2)
        self.assertEqual(obj1['version'], 2)

    def test_legacy_footprint_route_unchanged(self):
        foot = (Decimal('0'), Decimal('1.000000000000000001'),
                None, Decimal('2'), Decimal('0'), Decimal('2'))
        code, _, data, _, _ = invoke('/v1/footprint?symbol=BTCUSDT', records=[foot])
        self.assertEqual(code, 200)
        self.assertEqual(data['version'], 2)
        self.assertEqual(data['rows'][0]['price'], '1.000000000000000001')

    def test_source_timestamp_outside_window_refused(self):
        code, _, data, _, _ = invoke(BASE, records=[record(180000)])
        self.assertEqual(code, 503)
        self.assertEqual(data, {'error': 'source unavailable'})

    def test_symbol_and_asof_roundtrip_exact(self):
        path = BASE.replace('symbol=BTCUSDT', 'symbol=ETHUSDT').replace('as_of_ms=120000', 'as_of_ms=600000')
        code, _, data, _, _ = invoke(path, records=[record(0), record(60000)])
        self.assertEqual(code, 200)
        self.assertEqual(data['symbol'], 'ETHUSDT')
        self.assertEqual(data['selection']['as_of_ms'], 600000)
        self.assertFalse(data['paper_admitted'])


if __name__ == '__main__':
    unittest.main()
