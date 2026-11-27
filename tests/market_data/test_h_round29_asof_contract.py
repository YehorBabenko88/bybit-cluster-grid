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
        asof = BOUNDARY + 60000
        older = [copy.deepcopy(x) for x in batch]
        with self.assertRaises(ProvenanceReadError):
            historical_asof_snapshot(
                "BTCUSDT", "5m", 1, BOUNDARY, asof,
                reader=lambda *_:copy.deepcopy(older),
                now_ms=asof + 3600000)
        # Original per-minute ingestion is NOW > asof, so refusal is mandatory.

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
        self.assertEqual(page["source_declared_quality"], ["GOOD"])
        self.assertEqual(page["schema"],"market_data.qualified-mtf-envelope.v1")
        self.assertEqual(page["status"],"PARTIAL")
        self.assertFalse(page["paper_admitted"])
        self.assertFalse(page["execution_authority"])
        self.assertFalse(page["trading_authorized"])


if __name__ == "__main__":
    unittest.main()
