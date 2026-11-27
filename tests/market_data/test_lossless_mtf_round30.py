"""B ROUND30: executable canonical Math lossless LIVE/historical source tests.

Synthetic 1m provenance fixtures; no external Bybit/Consul/PostgreSQL or
production admission. The *actual* market_data_v2 functions are imported.
"""
import copy
import unittest
from unittest.mock import patch

from test_qualified_rollup_round27 import BOUNDARY, NOW, fixture_minutes, handler
from market_data.provenance import digest
from market_data_v2.qualified_read_contract import ProvenanceReadError
from market_data_v2.read_api import (
    EXACT_HISTORICAL_ROUTE, EXACT_ROLLUP_ROUTE,
    historical_asof_snapshot, qualified_rollup_snapshot,
)
from decimal import Decimal
from market_math import executed_volume_delta, exact_sum


def accurate_fixture(count):
    return fixture_minutes(count, ingestion_ms=BOUNDARY)


class LosslessMtfRound30(unittest.TestCase):
    def test_exact_5m_and_15m_schema_and_hash_bind(self):
        for tf, bars in (("5m", 3), ("15m", 5)):
            minutes = (5 if tf == "5m" else 15) * bars
            records = accurate_fixture(minutes)
            got = qualified_rollup_snapshot(
                "BTCUSDT", tf, bars,
                reader=lambda *_: copy.deepcopy(records), now_ms=NOW,
                exact=True)
            with self.subTest(tf=tf):
                self.assertEqual(got["schema"], "market_data.qualified-mtf-envelope.v2")
                self.assertEqual(got["api_version"], {"major": 2, "minor": 1})
                self.assertEqual(got["decimal_contract"], "CANONICAL_MATH_EXACT_SOURCE_VALUES")
                self.assertEqual(got["numeric_presentation"], "DECIMAL_STRING_LOSSLESS")
                self.assertEqual(got["status"], "PARTIAL")
                self.assertEqual(got["coverage"]["missing_minutes"], 0)
                self.assertFalse(got["execution_authority"])
                self.assertFalse(got["trading_authorized"])
                self.assertFalse(got["paper_admitted"])
                self.assertEqual(got["dataset_fingerprint"],
                    digest({k:v for k,v in got.items() if k!="dataset_fingerprint"}))
                for row in got["rows"]:
                    buy=Decimal(row["buy_volume_decimal"])
                    sell=Decimal(row["sell_volume_decimal"])
                    self.assertEqual(Decimal(row["volume_decimal"]),
                                     exact_sum((buy,sell)))
                    self.assertEqual(Decimal(row["delta_decimal"]),
                                     executed_volume_delta(buy,sell))
                    self.assertEqual(row["volume_decimal"],
                                     str(exact_sum((buy,sell))))
                    self.assertEqual(row["delta_decimal"],
                                     str(executed_volume_delta(buy,sell)))

    def test_huge_decimal_delta_retained_without_false_parity_refusal(self):
        records=accurate_fixture(5)
        # Canonical Math source is v1 binary64 already, but aggregate sums may
        # lose a small difference in JSON binary64. No fabricated raw precision.
        records[1]["candle"]["buy_volume"]=1.01
        records[1]["candle"]["sell_volume"]=1.0
        records[1]["candle"]["delta"]=0.01
        records[1]["levels"][0]["buy_volume"]=1.01
        records[1]["levels"][0]["sell_volume"]=1.0
        records[1]["levels"][0]["delta"]=0.01
        records[1]["levels"][0]["volume"]=2.01
        records[0]["candle"]["buy_volume"]=1e16
        records[0]["candle"]["sell_volume"]=1e16
        records[0]["candle"]["delta"]=0.0
        records[0]["levels"][0]["buy_volume"]=1e16
        records[0]["levels"][0]["sell_volume"]=1e16
        records[0]["levels"][0]["delta"]=0.0
        records[0]["levels"][0]["volume"]=2e16
        for row in records:
            row["dataset_fingerprint"]=digest({
                k:v for k,v in row.items() if k!="dataset_fingerprint"})
        got=qualified_rollup_snapshot(
            "BTCUSDT","5m",1,reader=lambda *_: records,now_ms=NOW,exact=True)
        row=got["rows"][0]
        self.assertEqual(row["buy_volume_decimal"],"10000000000000004.01")
        self.assertEqual(row["sell_volume_decimal"],"10000000000000004.0")
        self.assertEqual(row["volume_decimal"],"20000000000000008.01")
        self.assertEqual(row["delta_decimal"],"0.01")
        self.assertEqual(row["buy_volume"],row["sell_volume"])
        self.assertFalse(got["paper_admitted"])

    def test_historical_source_only_and_lookahead(self):
        rows=accurate_fixture(15)
        cutoff=BOUNDARY+60000
        got=historical_asof_snapshot(
            "BTCUSDT","5m",3,BOUNDARY,cutoff,
            reader=lambda *_:copy.deepcopy(rows),
            now_ms=BOUNDARY+3600000,exact=True)
        self.assertEqual(got["schema"],
                         "market_data.historical-as-of-mtf-envelope.v2")
        self.assertEqual(got["reason"],"HISTORICAL_AS_OF_SOURCE_ONLY")
        self.assertEqual(got["freshness_mode"],"HISTORICAL_AS_OF")
        self.assertEqual(got["historical_source_trust"],
                         "NOT_INDEPENDENTLY_ATTESTED")
        self.assertFalse(got["trading_authorized"])
        self.assertEqual(got["dataset_fingerprint"],
                         digest({k:v for k,v in got.items()
                                 if k!="dataset_fingerprint"}))
        late=accurate_fixture(15)
        for rec in late:
            rec["ingestion_ms"]=cutoff+1000
            rec["dataset_fingerprint"]=digest({
                k:v for k,v in rec.items() if k!="dataset_fingerprint"})
        with self.assertRaises(ProvenanceReadError):
            historical_asof_snapshot("BTCUSDT","5m",3,
                BOUNDARY,cutoff,reader=lambda *_:late,
                now_ms=BOUNDARY+3600000,exact=True)

    def test_legacy_v1_layout_unchanged(self):
        rows=accurate_fixture(5)
        legacy=qualified_rollup_snapshot("BTCUSDT","5m",1,
            reader=lambda *_:rows,now_ms=NOW,exact=False)
        self.assertEqual(legacy["schema"],"market_data.qualified-mtf-envelope.v1")
        self.assertNotIn("decimal_contract",legacy)
        self.assertNotIn("volume_decimal",legacy["rows"][0])
        self.assertFalse(legacy["execution_authority"])

    def test_invalid_exact_query_must_not_touch_canonical_reader(self):
        bad=(EXACT_ROLLUP_ROUTE+"?symbol=BTCUSDT&timeframe=1h&limit=1",
             EXACT_ROLLUP_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=6",
             EXACT_ROLLUP_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=1&extra=1",
             EXACT_HISTORICAL_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=1&before_ms=0&as_of_ms=60000")
        for path in bad:
            h=handler(path)
            with patch("market_data.history_api.immutable_minutes",
                       side_effect=AssertionError("no invalid data IO")):
                h.do_GET()
            self.assertEqual(h.results[0][0],400)

    def test_managed_exact_route_rechecks_lease_post_read(self):
        path=EXACT_ROLLUP_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=1"
        h=handler(path)
        with patch("market_data.history_api.immutable_minutes",
                   return_value=accurate_fixture(5)) as reader:
            with patch("market_data_v2.read_api.time.time",
                       return_value=NOW/1000):
                h.do_GET()
        self.assertEqual(h.results[0][0],200)
        self.assertEqual(h.results[0][1]["schema"],"market_data.qualified-mtf-envelope.v2")
        self.assertEqual(h.server.startup_admission.calls,3)
        reader.assert_called_once()
        revoked=handler(path)
        revoked.server.startup_admission.verdicts=[True,True,False]
        with patch("market_data.history_api.immutable_minutes",
                   return_value=accurate_fixture(5)):
            with patch("market_data_v2.read_api.time.time",
                       return_value=NOW/1000):
                revoked.do_GET()
        self.assertEqual(revoked.results[0][0],503)
        self.assertNotIn("rows",revoked.results[0][1])

    def test_missing_or_mixed_epoch_denied(self):
        rows=accurate_fixture(5)
        for sample in (rows[:-1], [*rows[:2],*accurate_fixture(5)[2:]]):
            with self.assertRaises(ProvenanceReadError):
                qualified_rollup_snapshot("BTCUSDT","5m",1,
                    reader=lambda *_:sample,now_ms=NOW,exact=True)


if __name__ == "__main__":
    unittest.main()
