"""H ROUND32 original B308 v2 cursor guard and no-data-IO acceptance.

Source execution is delegated to the original Grid read_api implementation.
No provider, SQL setup, Math clone, trade authority or extra handler.
"""
import copy
import unittest

from h_mtf_fixture import BOUNDARY, NOW, minutes
from market_data_v2.read_api import (
    qualified_rollup_snapshot, historical_asof_snapshot,
)


class HRound32ExactCursor(unittest.TestCase):
    def test_live_bad_cursor_fails_before_reader(self):
        def forbidden(*_args, **_kwargs):
            self.fail("invalid LIVE cursor invoked source reader")
        for timeframe in ("5m", "15m"):
            bad = (0, -1, True, 1.0, "01", "1e3", BOUNDARY + 60000,
                   NOW + 60000, 2**63)
            for cursor in bad:
                with self.subTest(timeframe=timeframe, cursor=repr(cursor)):
                    with self.assertRaises(ValueError):
                        qualified_rollup_snapshot(
                            "BTCUSDT", timeframe, 1, before_ms=cursor,
                            reader=forbidden, now_ms=NOW, exact=True)

    def test_history_partial_bucket_denied_before_reader(self):
        def forbidden(*_args, **_kwargs):
            self.fail("invalid historical cursor invoked source reader")
        for timeframe in ("5m", "15m"):
            for cursor in (0, BOUNDARY + 60000, True, "01", "1e3"):
                with self.subTest(timeframe=timeframe, cursor=repr(cursor)):
                    with self.assertRaises(ValueError):
                        historical_asof_snapshot(
                            "BTCUSDT", timeframe, 1, cursor,
                            BOUNDARY + 120000, reader=forbidden,
                            now_ms=BOUNDARY + 3600000, exact=True)

    def test_exact_mode_must_be_literal_bool_before_data_read(self):
        def forbidden(*_args, **_kwargs):
            self.fail("nonliteral exact mode invoked source reader")
        for bad in (1, "True", None, 0):
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    qualified_rollup_snapshot(
                        "BTCUSDT", "5m", 1, before_ms=BOUNDARY,
                        reader=forbidden, now_ms=NOW, exact=bad)
                with self.assertRaises(ValueError):
                    historical_asof_snapshot(
                        "BTCUSDT", "5m", 1, BOUNDARY, BOUNDARY + 60000,
                        reader=forbidden, now_ms=BOUNDARY + 3600000,
                        exact=bad)

    def test_valid_5m_historical_asof_keeps_source_only_and_decimal(self):
        records = minutes(5, buy=1.0, sell=0.5)
        page = historical_asof_snapshot(
            "BTCUSDT", "5m", 1, BOUNDARY, BOUNDARY + 60000,
            reader=lambda *_: copy.deepcopy(records),
            now_ms=BOUNDARY + 3600000, exact=True)
        self.assertEqual(page["schema"],
                         "market_data.historical-as-of-mtf-envelope.v2")
        self.assertEqual(page["source_numeric_precision"],
                         "STORED_1M_JSON_NUMBERS_NOT_PROVIDER_RAW")
        self.assertEqual(page["status"], "PARTIAL")
        self.assertFalse(page["paper_admitted"])
        self.assertFalse(page["trading_authorized"])
        self.assertEqual(page["rows"][-1]["end_ms"], BOUNDARY - 1)
        self.assertEqual(page["rows"][-1]["delta_decimal"], "2.5")

    def test_legacy_v1_cursor_is_not_silently_replaced(self):
        records = minutes(5, buy=1.0, sell=0.5)
        result = qualified_rollup_snapshot(
            "BTCUSDT", "5m", 1,
            reader=lambda *_: copy.deepcopy(records),
            now_ms=NOW, exact=False)
        self.assertEqual(result["schema"],
                         "market_data.qualified-mtf-envelope.v1")
        self.assertNotIn("decimal_contract", result)
        self.assertFalse(result["execution_authority"])


if __name__ == "__main__":
    unittest.main()
