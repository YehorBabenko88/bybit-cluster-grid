"""H R29 exact-source Grid #305 ↔ Terminan #130 compatibility regressions.

The locally supplied original Terminan consumer is dynamically imported by the
integration runner. This file never replaces original code, never trusts an
unmanaged transport, and never grants trading authority. Imported B/Terminan
SHAs are pinned in H181, not automatically installed by this test.
"""
import copy
from decimal import Decimal
import unittest

from market_data_v2.read_api import qualified_rollup_snapshot, historical_asof_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError
from market_math import exact_sum, executed_volume_delta
from test_h_round28_mtf_parity import minutes, NOW, BOUNDARY


class HRound29ExactMathAndAsOf(unittest.TestCase):
    def test_grid_delta_uses_precise_input_not_float_presentation(self):
        # Explicitly prove the numerical trap; original B Round28 synthetic
        # test also validates equivalent source-valid 1m records.
        buy = Decimal("10000000000000004.01")
        sell = Decimal("10000000000000004")
        original_delta = executed_volume_delta(buy, sell)
        self.assertEqual(original_delta, Decimal("0.01"))
        self.assertEqual(float(buy), float(sell))
        self.assertEqual(float(buy) - float(sell), 0.0)

    def test_historical_asof_cuts_off_future_ingestion(self):
        batch = minutes(5)
        asof = BOUNDARY
        older = [copy.deepcopy(x) for x in batch]
        with self.assertRaises(ProvenanceReadError):
            historical_asof_snapshot(
                "BTCUSDT", "5m", 1, BOUNDARY, asof,
                reader=lambda *_:copy.deepcopy(older),
                now_ms=asof + 3600000)
        # Original minute fixture ingests at NOW=BOUNDARY+45000 > asof.\n        # Historical query must refuse this unobserved-at-asof record.

    def test_live_old_source_is_not_historical_partial(self):
        batch = minutes(5)
        with self.assertRaises(ProvenanceReadError):
            qualified_rollup_snapshot(
                "BTCUSDT","5m",1,
                reader=lambda *_:copy.deepcopy(batch),now_ms=NOW+180000)

    def test_grid_live_mtf_producer_quality_contract(self):
        rows = minutes(5)
        page=qualified_rollup_snapshot(
            "BTCUSDT","5m",1,
            reader=lambda *_:copy.deepcopy(rows), now_ms=NOW)
        self.assertNotIn("source_declared_quality",page)
        self.assertEqual(page["schema"],"market_data.qualified-mtf-envelope.v1")
        self.assertEqual(page["status"],"PARTIAL")
        self.assertFalse(page["paper_admitted"])
        self.assertFalse(page["execution_authority"])
        self.assertFalse(page["trading_authorized"])


    def test_grid_b306_rejects_uncheckable_binary64_delta(self):
        from test_qualified_rollup_round27 import fixture_minutes
        from market_data.provenance import digest
        rows = fixture_minutes(5, ingestion_ms=BOUNDARY)
        for i, item in enumerate(rows):
            buy = 1e16 if i == 0 else (1.01 if i == 1 else 1.0)
            sell = 1e16 if i == 0 else 1.0
            delta = 0.01 if i == 1 else 0.0
            item["candle"].update(buy_volume=buy, sell_volume=sell, delta=delta)
            item["levels"][0].update(
                buy_volume=buy, sell_volume=sell, delta=delta, volume=buy+sell)
            item["dataset_fingerprint"] = digest({
                k:v for k,v in item.items() if k != "dataset_fingerprint"})
        with self.assertRaisesRegex(
                ProvenanceReadError, "ROLLUP_BINARY64_PARITY_UNAVAILABLE"):
            qualified_rollup_snapshot(
                "BTCUSDT", "5m", 1, reader=lambda *_:copy.deepcopy(rows),
                now_ms=NOW)


if __name__ == "__main__":
    unittest.main()
