"""Synthetic 1m -> 5m/15m source and managed HTTP negative regressions.

No live Bybit, PostgreSQL, Root authority or protected wheel is claimed.
"""
import copy
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from market_data.provenance import minute_record, producer, digest
from market_data_v2.read_api import (
    Handler, ROLLUP_ROUTE, ROUTE, qualified_rollup_snapshot)
from market_data_v2.qualified_read_contract import ProvenanceReadError

NOW = (1800000120000 // 900000) * 900000 + 45000
BOUNDARY = (NOW // 900000) * 900000


def fixture_minutes(count, *, shift=0, ingestion_ms=None):
    source = producer("round27-synthetic", "a" * 40,
                      "wss://stream.bybit.com/v5/public/linear")
    start = BOUNDARY - count * 60000 + shift
    records = []
    if ingestion_ms is None:
        ingestion_ms = NOW + (60000 if shift else 0)
    for i in range(count):
        minute = start + i * 60000
        row = {
            "symbol": "BTCUSDT", "start_ms": minute,
            "source_event_start_ms": minute + 1,
            "source_event_end_ms": minute + 59000,
            "source_provenance": source,
            "open": 1.0, "high": 2.0, "low": 1.0, "close": 2.0,
            "buy_volume": 1.0, "sell_volume": 0.0,
            "delta": 1.0, "trade_count": 1,
            "poc_price": 2.0, "quality_status": "GOOD",
            "quality_reasons": [],
            "levels": [{
                "price": 2.0, "buy_volume": 1.0,
                "sell_volume": 0.0, "delta": 1.0,
                "volume": 1.0, "buy_count": 1, "sell_count": 0,
            }],
        }
        records.append(minute_record(row, ingestion_ms,
                                     "round27-synthetic"))
    return records


class Admission:
    def __init__(self, verdicts=(True, True, True)):
        self.verdicts = list(verdicts)
        self.calls = 0

    def require_current(self):
        self.calls += 1
        return self.verdicts.pop(0) if self.verdicts else False


def handler(path, *, admission=None, identity=True, token="b" * 64):
    item = object.__new__(Handler)
    item.server = SimpleNamespace(
        module_identity={"instance_token": "b" * 64} if identity else None,
        startup_admission=admission if admission is not None else Admission())
    item.headers = Message()
    if token is not None:
        item.headers.add_header("Authorization", "Bearer " + token)
    item.path = path
    item.results = []
    item._json = lambda code, data: item.results.append((code, data))
    return item


class QualifiedRollupRound27Tests(unittest.TestCase):
    def test_5m_and_15m_real_grid_minute_qualifier_source(self):
        for timeframe, limit, total in (("5m", 3, 15), ("15m", 5, 75)):
            rows = fixture_minutes(total)
            reads = []
            def read(symbol, size, before):
                reads.append((symbol, size, before))
                return copy.deepcopy(rows)
            output = qualified_rollup_snapshot(
                "BTCUSDT", timeframe, limit, reader=read, now_ms=NOW)
            with self.subTest(timeframe=timeframe):
                self.assertEqual(reads, [("BTCUSDT", total, 2**63-1)])
                self.assertEqual(output["schema"],
                                 "market_data.qualified-rollup-envelope.v1")
                self.assertEqual(output["status"], "PARTIAL")
                self.assertEqual(output["timeframe"], timeframe)
                self.assertEqual(output["source_timeframe"], "1m")
                self.assertEqual(output["source_minutes"], total)
                self.assertEqual(len(output["rows"]), limit)
                self.assertEqual(output["coverage"]["missing_minutes"], 0)
                self.assertTrue(output["record_integrity"] == "VERIFIED")
                self.assertFalse(output["execution_authority"])
                self.assertFalse(output["paper_admitted"])
                self.assertFalse(output["trading_authorized"])
                self.assertFalse(output["immutable"])
                self.assertEqual(output["exchange_completeness"], "NOT_ATTESTED")
                self.assertEqual(output["source_authenticity"],
                                 "NOT_INDEPENDENTLY_ATTESTED")
                self.assertEqual(output["rows"][0]["trade_count"],
                                 total // limit)
                self.assertEqual(output["rows"][0]["buy_volume"],
                                 float(total // limit))
                self.assertEqual(output["rows"][0]["delta"],
                                 float(total // limit))
                self.assertEqual(output["rows"][0]["open"], 1.0)
                self.assertEqual(output["rows"][0]["high"], 2.0)
                self.assertEqual(output["rows"][0]["low"], 1.0)
                self.assertEqual(output["rows"][0]["close"], 2.0)
                self.assertEqual(len(output["rows"][0]["source_minute_fingerprints"]),
                                 total // limit)
                self.assertEqual(output["dataset_fingerprint"],
                                 digest({k: v for k, v in output.items()
                                         if k != "dataset_fingerprint"}))

    def test_missing_minute_and_partial_bucket_are_denied(self):
        rows = fixture_minutes(15)
        for invalid in (rows[:14], rows[:7] + rows[8:]):
            with self.subTest(count=len(invalid)), self.assertRaises(ProvenanceReadError):
                qualified_rollup_snapshot(
                    "BTCUSDT", "5m", 3, reader=lambda *_: invalid, now_ms=NOW)

    def test_mixed_epoch_and_stale_read_never_upgrade(self):
        rows = fixture_minutes(15)
        different = fixture_minutes(15)
        mixed = copy.deepcopy(rows)
        mixed[3] = different[3]
        self.assertNotEqual(mixed[3]["source"]["epoch"], rows[0]["source"]["epoch"])
        for records, clock in ((mixed, NOW), (rows, NOW + 180000)):
            with self.subTest(clock=clock), self.assertRaises(ProvenanceReadError):
                qualified_rollup_snapshot(
                    "BTCUSDT", "5m", 3, reader=lambda *_: records, now_ms=clock)

    def test_unaligned_start_rejected_with_all_15_records(self):
        rows = fixture_minutes(15, shift=60000)
        with self.assertRaisesRegex(ProvenanceReadError, "ROLLUP_ALIGNMENT"):
            qualified_rollup_snapshot(
                "BTCUSDT", "5m", 3,
                reader=lambda *_: rows, now_ms=NOW+60000)

    def test_open_last_minute_is_refused_even_when_events_are_observed(self):
        rows = fixture_minutes(15, ingestion_ms=BOUNDARY-1000)
        # Source has an observed trade, but the UTC minute has not closed.
        with self.assertRaisesRegex(ProvenanceReadError,
                                    "ROLLUP_CLOSED_BAR_REQUIRED"):
            qualified_rollup_snapshot(
                "BTCUSDT", "5m", 3,
                reader=lambda *_: rows, now_ms=BOUNDARY-500)

    def test_bad_interval_limits_and_cursor_never_access_source(self):
        def forbidden(*_):
            self.fail("invalid request attempted source read")
        for timeframe, limit, cursor in (
            ("1h", 1, None), ("1m", 1, None),
            ("15m", 6, None), ("5m", 0, None),
            ("5m", "01", None), ("5m", True, None),
            ("5m", 2, "0"), ("5m", 2, True),
        ):
            with self.subTest(timeframe=timeframe,limit=limit,cursor=cursor):
                with self.assertRaises(ValueError):
                    qualified_rollup_snapshot(
                        "BTCUSDT", timeframe, limit, cursor,
                        reader=forbidden, now_ms=NOW)

    def test_managed_single_listener_and_lease_recheck(self):
        path = ROLLUP_ROUTE + "?symbol=BTCUSDT&timeframe=5m&limit=3"
        h = handler(path)
        with patch("market_data.history_api.immutable_minutes",
                   return_value=fixture_minutes(15)) as read:
            with patch("market_data_v2.read_api.time.time",
                       return_value=NOW / 1000):
                h.do_GET()
        self.assertEqual(h.results[0][0], 200)
        self.assertEqual(h.results[0][1]["status"], "PARTIAL")
        read.assert_called_once_with("BTCUSDT", 15, 2**63-1)
        self.assertEqual(h.server.startup_admission.calls, 3)

    def test_unmanaged_wrong_bearer_and_post_read_revoke_no_rows(self):
        path = ROLLUP_ROUTE + "?symbol=BTCUSDT&timeframe=15m&limit=1"
        for h in (handler(path, identity=False), handler(path, token=None),
                  handler(path, token="c"*64)):
            with patch("market_data.history_api.immutable_minutes",
                       side_effect=AssertionError("unauthorized source read")):
                h.do_GET()
            self.assertIn(h.results[0][0], (401, 503))
        h = handler(path, admission=Admission((True,True,False)))
        with patch("market_data.history_api.immutable_minutes",
                   return_value=fixture_minutes(15)):
            with patch("market_data_v2.read_api.time.time",
                       return_value=NOW / 1000):
                h.do_GET()
        self.assertEqual(h.results, [(503, {"error": "CURRENT_ADMISSION_REQUIRED"})])

    def test_invalid_rollup_fields_never_access_sql(self):
        prefix = ROLLUP_ROUTE + "?"
        for query in ("symbol=BTCUSDT&timeframe=1h&limit=1",
                      "symbol=BTCUSDT&timeframe=5m&limit=6",
                      "symbol=BTCUSDT&timeframe=5m&limit=01",
                      "symbol=BTCUSDT&timeframe=5m&limit=1&other=x",
                      "symbol=BTCUSDT&timeframe=5m&timeframe=15m&limit=1"):
            h = handler(prefix + query)
            with patch("market_data.history_api.immutable_minutes",
                       side_effect=AssertionError("invalid source read")):
                h.do_GET()
            self.assertEqual(h.results[0][0], 400)

    def test_legacy_1m_route_constant_still_unchanged(self):
        self.assertEqual(ROUTE, "/internal/v2/candles/qualified")
        self.assertNotEqual(ROLLUP_ROUTE, ROUTE)


if __name__ == "__main__":
    unittest.main()
