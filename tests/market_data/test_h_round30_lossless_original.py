"""H ROUND30 independent original Grid v2 lossless MTF acceptance tests.

Run with the exact B307 source and canonical market_math; synthetic 1m only.
No new numeric kernel, raw exchange attestations, SQL writer or trade authority.
"""
import copy
from decimal import Decimal
import unittest

from h_mtf_fixture import NOW, BOUNDARY, minutes
from market_data.provenance import digest
from market_data_v2.read_api import qualified_rollup_snapshot, historical_asof_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError
from market_math import exact_sum, executed_volume_delta


def _high_precision_source():
    rows = minutes(5, buy=1.0, sell=1.0)
    for i, item in enumerate(rows):
        buy = 1e16 if i == 0 else (1.01 if i == 1 else 1.0)
        sell = 1e16 if i == 0 else 1.0
        delta = 0.01 if i == 1 else 0.0
        item["candle"].update(buy_volume=buy, sell_volume=sell, delta=delta)
        item["levels"][0].update(
            buy_volume=buy, sell_volume=sell, delta=delta, volume=buy+sell)
        item["dataset_fingerprint"] = digest({
            key:value for key,value in item.items() if key != "dataset_fingerprint"})
    return rows


class HLosslessRound30OriginalGridTests(unittest.TestCase):
    def test_exact_5m_fractional_delta_and_total_preserved(self):
        rows = _high_precision_source()
        output = qualified_rollup_snapshot(
            "BTCUSDT", "5m", 1, reader=lambda *_:copy.deepcopy(rows),
            now_ms=NOW, exact=True)
        self.assertEqual(output["schema"], "market_data.qualified-mtf-envelope.v2")
        self.assertEqual(output["api_version"], {"major":2, "minor":1})
        self.assertEqual(output["decimal_contract"], "CANONICAL_MATH_EXACT_STORED_1M")
        self.assertEqual(output["source_numeric_precision"],
                         "STORED_1M_JSON_NUMBERS_NOT_PROVIDER_RAW")
        self.assertEqual(len(output["rows"]), 1)
        row = output["rows"][0]
        self.assertEqual(row["buy_volume_decimal"], "10000000000000004.01")
        self.assertEqual(row["sell_volume_decimal"], "10000000000000004")
        self.assertEqual(row["volume_decimal"], "20000000000000008.01")
        self.assertEqual(row["delta_decimal"], "0.01")
        self.assertEqual(row["buy_volume"], row["sell_volume"])
        self.assertEqual(Decimal(row["volume_decimal"]), exact_sum((
            Decimal(row["buy_volume_decimal"]), Decimal(row["sell_volume_decimal"]))))
        self.assertEqual(Decimal(row["delta_decimal"]), executed_volume_delta(
            Decimal(row["buy_volume_decimal"]), Decimal(row["sell_volume_decimal"])))
        for key in ("paper_admitted","execution_authority","trading_authorized","immutable"):
            self.assertIs(output[key], False)
        self.assertEqual(output["dataset_fingerprint"], digest({
            key:value for key,value in output.items()
            if key != "dataset_fingerprint"}))

    def test_exact_15m_full_closed_coverage_and_negative_delta(self):
        rows = minutes(15, buy=0.1, sell=0.3)
        output = qualified_rollup_snapshot(
            "BTCUSDT","15m",1,reader=lambda *_:copy.deepcopy(rows),
            now_ms=NOW,exact=True)
        self.assertEqual(output["source_minutes"],15)
        self.assertEqual(output["coverage"]["missing_minutes"],0)
        self.assertEqual(output["rows"][0]["delta_decimal"],"-3")
        self.assertEqual(len(output["rows"][0]["source_minute_fingerprints"]),15)

    def test_fixed_ascii_exponent_free_decimal_wire(self):
        rows=minutes(5,buy=1e16,sell=0.0)
        output=qualified_rollup_snapshot(
            "BTCUSDT","5m",1,reader=lambda *_:copy.deepcopy(rows),
            now_ms=NOW,exact=True)
        value=output["rows"][0]["buy_volume_decimal"]
        self.assertEqual(value,"50000000000000000")
        self.assertNotIn("e",value.lower())
        self.assertEqual(Decimal(value),Decimal("5E+16"))

    def test_historical_exact_asof_without_lookahead(self):
        rows=minutes(5,buy=1.0,sell=0.5)
        data=historical_asof_snapshot(
            "BTCUSDT","5m",1,BOUNDARY,BOUNDARY+60000,
            reader=lambda *_:copy.deepcopy(rows),
            now_ms=BOUNDARY+3600000,exact=True)
        self.assertEqual(data["schema"],"market_data.historical-as-of-mtf-envelope.v2")
        self.assertEqual(data["freshness_mode"],"HISTORICAL_AS_OF")
        self.assertEqual(data["historical_source_trust"],"NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(data["source_numeric_precision"],
                         "STORED_1M_JSON_NUMBERS_NOT_PROVIDER_RAW")
        self.assertFalse(data["paper_admitted"])
        with self.assertRaises(ProvenanceReadError):
            historical_asof_snapshot(
                "BTCUSDT","5m",1,BOUNDARY,BOUNDARY,
                reader=lambda *_:copy.deepcopy(rows),
                now_ms=BOUNDARY+3600000,exact=True)

    def test_degraded_or_mixed_source_refused_without_unsafe_fallback(self):
        rows=minutes(5)
        degraded=copy.deepcopy(rows)
        degraded[0]["quality_status"]="DEGRADED"
        degraded[0]["quality_reasons"]=["SOURCE_GAP"]
        degraded[0]["dataset_fingerprint"]=digest({
            k:v for k,v in degraded[0].items() if k!="dataset_fingerprint"})
        mixed=copy.deepcopy(rows)
        mixed[2]=minutes(5)[2]
        for original in (degraded,mixed,rows[:4]):
            with self.subTest(count=len(original)), self.assertRaises(ProvenanceReadError):
                qualified_rollup_snapshot(
                    "BTCUSDT","5m",1,
                    reader=lambda *_:copy.deepcopy(original),
                    now_ms=NOW,exact=True)

    def test_bad_limit_never_invokes_source(self):
        def forbidden(*_):
            self.fail("invalid query invoked source")
        with self.assertRaises(ValueError):
            qualified_rollup_snapshot(
                "BTCUSDT","15m",6,reader=forbidden,now_ms=NOW,exact=True)

    def test_existing_v1_path_still_unmodified(self):
        rows=minutes(5,buy=1.0,sell=0.5)
        legacy=qualified_rollup_snapshot(
            "BTCUSDT","5m",1,reader=lambda *_:copy.deepcopy(rows),
            now_ms=NOW,exact=False)
        self.assertEqual(legacy["schema"],"market_data.qualified-mtf-envelope.v1")
        self.assertNotIn("decimal_contract",legacy)
        self.assertNotIn("volume_decimal",legacy["rows"][0])
        self.assertFalse(legacy["trading_authorized"])


if __name__ == "__main__":
    unittest.main()
