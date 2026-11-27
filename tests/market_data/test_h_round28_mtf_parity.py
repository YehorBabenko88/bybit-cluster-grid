"""H ROUND28 independently execute canonical Grid qualified 5m/15m against Math.

No provider, SQL, exchange, extra writer, network or trade execution.
This test exercises B's original reader/qualifier code via its injected
read-only reader seam and Math's established exact_sum/delta kernels.
"""
import copy
from decimal import Decimal
import unittest

from market_data.provenance import producer, minute_record, digest
from market_data_v2.read_api import qualified_rollup_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError
from market_math import exact_sum, executed_volume_delta

NOW = (1800000120000 // 900000) * 900000 + 45000
BOUNDARY = (NOW // 900000) * 900000


def minutes(width, buy=0.1, sell=0.3):
    source = producer("h-r28-synthetic", "a"*40,
                      "wss://stream.bybit.com/v5/public/linear")
    start = BOUNDARY - width * 60000
    records = []
    for i in range(width):
        tick = start + i * 60000
        row = {
            "symbol": "BTCUSDT", "start_ms": tick,
            "source_event_start_ms":tick + 1,
            "source_event_end_ms":tick + 59000,
            "source_provenance": source,
            "open": 1.0, "high":2.0, "low":1.0, "close":2.0,
            "buy_volume":buy, "sell_volume":sell,
            "delta":buy-sell, "trade_count":2, "poc_price":2.0,
            "quality_status":"GOOD", "quality_reasons":[],
            "levels":[{"price":2.0, "buy_volume":buy, "sell_volume":sell,
                       "delta":buy-sell, "volume":buy+sell,
                       "buy_count":1, "sell_count":1}]
        }
        records.append(minute_record(row, NOW, "h-r28-synthetic"))
    return records


class HRound28GridMathParity(unittest.TestCase):
    def test_exact_math_parity_five_and_fifteen_minute(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            for buy, sell in ((0.1,0.3),(1.0,0.5),(1e16,1.0)):
                with self.subTest(timeframe=timeframe, buy=buy, sell=sell):
                    original = minutes(width,buy,sell)
                    result = qualified_rollup_snapshot(
                        "BTCUSDT",timeframe,1,
                        reader=lambda *_:copy.deepcopy(original),now_ms=NOW)
                    self.assertEqual(result["schema"],
                                     "market_data.qualified-mtf-envelope.v1")
                    self.assertEqual(result["status"],"PARTIAL")
                    self.assertEqual(result["source_minutes"],width)
                    self.assertEqual(result["coverage"]["missing_minutes"],0)
                    row = result["rows"][0]
                    expected_buy = exact_sum(Decimal(str(r["candle"]["buy_volume"]))
                                             for r in original)
                    expected_sell = exact_sum(Decimal(str(r["candle"]["sell_volume"]))
                                              for r in original)
                    self.assertEqual(row["buy_volume"],float(expected_buy))
                    self.assertEqual(row["sell_volume"],float(expected_sell))
                    self.assertEqual(
                        row["delta"],
                        float(executed_volume_delta(
                            expected_buy, expected_sell))))
                    self.assertEqual(len(row["source_minute_fingerprints"]),width)
                    self.assertEqual(result["dataset_fingerprint"],digest({
                        key:value for key,value in result.items()
                        if key!="dataset_fingerprint"}))
                    for gate in ("execution_authority","trading_authorized",
                                 "paper_admitted","immutable"):
                        self.assertIs(result[gate],False)
                    self.assertEqual(result["source_authenticity"],
                                     "NOT_INDEPENDENTLY_ATTESTED")
                    self.assertEqual(result["exchange_completeness"],"NOT_ATTESTED")

    def test_historical_stale_source_cannot_be_relabelled_partial(self):
        rows=minutes(5)
        with self.assertRaises(ProvenanceReadError):
            qualified_rollup_snapshot("BTCUSDT","5m",1,
                                     reader=lambda *_:copy.deepcopy(rows),
                                     now_ms=NOW+180000)

    def test_incomplete_and_mixed_source_refuse_without_rows(self):
        rows=minutes(5)
        other=minutes(5)
        self.assertNotEqual(rows[0]["source"]["epoch"],other[0]["source"]["epoch"])
        bad=copy.deepcopy(rows)
        bad[2]=other[2]
        for batch in (bad,rows[:4]):
            with self.subTest(count=len(batch)), self.assertRaises(ProvenanceReadError):
                qualified_rollup_snapshot("BTCUSDT","5m",1,
                                         reader=lambda *_:copy.deepcopy(batch),
                                         now_ms=NOW)


if __name__=="__main__":
    unittest.main()
