"""Round28: bounded historical as-of read on the original managed Grid v2 source.

All fixtures are synthetic; no live exchange, PostgreSQL or Root issuer.
"""
import copy
import unittest
from unittest.mock import patch
from test_qualified_rollup_round27 import (
    NOW, BOUNDARY, fixture_minutes, handler,
)
from market_data.provenance import digest
from market_data_v2.read_api import (
    HISTORICAL_ROUTE, historical_asof_snapshot, qualified_rollup_snapshot,
)
from market_data_v2.qualified_read_contract import ProvenanceReadError


class HistoricalAsOfRound28Tests(unittest.TestCase):
    def test_historical_closed_5m_and_15m_source_only(self):
        for tf, limit in (("5m", 3), ("15m", 5)):
            count = (5 if tf == "5m" else 15)*limit
            rows = fixture_minutes(count, ingestion_ms=BOUNDARY)
            observation = BOUNDARY+60000
            cutoff = BOUNDARY
            calls = []
            def read(symbol, n, before):
                calls.append((symbol,n,before))
                return copy.deepcopy(rows)
            out = historical_asof_snapshot(
                "BTCUSDT",tf,limit,cutoff,observation,
                reader=read,now_ms=observation+3600000)
            with self.subTest(tf=tf):
                self.assertEqual(calls,[("BTCUSDT",count,cutoff)])
                self.assertEqual(out["schema"],
                    "market_data.historical-as-of-mtf-envelope.v1")
                self.assertEqual(out["freshness_mode"],"HISTORICAL_AS_OF")
                self.assertEqual(out["as_of_ms"],observation)
                self.assertEqual(out["status"],"PARTIAL")
                self.assertEqual(out["reason"],"HISTORICAL_AS_OF_SOURCE_ONLY")
                self.assertEqual(out["live_freshness"],"NOT_APPLICABLE")
                self.assertEqual(out["historical_source_trust"],
                    "NOT_INDEPENDENTLY_ATTESTED")
                self.assertEqual(len(out["rows"]),limit)
                self.assertFalse(out["paper_admitted"])
                self.assertFalse(out["trading_authorized"])
                self.assertFalse(out["execution_authority"])
                self.assertFalse(out["immutable"])
                self.assertEqual(out["dataset_fingerprint"],
                    digest({k:v for k,v in out.items()
                            if k!="dataset_fingerprint"}))

    def test_live_freshness_original_gate_is_unchanged(self):
        rows=fixture_minutes(15,ingestion_ms=BOUNDARY)
        with self.assertRaisesRegex(ProvenanceReadError,
                                     "ROLLUP_SOURCE_NOT_QUALIFIED"):
            qualified_rollup_snapshot("BTCUSDT","5m",3,BOUNDARY,
                reader=lambda *_:rows,now_ms=BOUNDARY+3600000)

    def test_asof_lookahead_ingestion_refused(self):
        rows=fixture_minutes(15,ingestion_ms=BOUNDARY+120000)
        with self.assertRaisesRegex(ProvenanceReadError,
                                     "QUERY_HISTORICAL_LOOKAHEAD"):
            historical_asof_snapshot("BTCUSDT","5m",3,BOUNDARY,
                BOUNDARY+60000,reader=lambda *_:rows,
                now_ms=BOUNDARY+3600000)

    def test_asof_wrong_symbol_and_invalid_cursor_never_read(self):
        def forbidden(*_):self.fail("invalid query caused SQL")
        for args in (
            ("bad-symbol","5m",1,BOUNDARY,BOUNDARY+60000),
            ("BTCUSDT","4h",1,BOUNDARY,BOUNDARY+60000),
            ("BTCUSDT","5m",6,BOUNDARY,BOUNDARY+60000),
            ("BTCUSDT","5m",1,BOUNDARY+1,BOUNDARY+60000),
            ("BTCUSDT","5m",1,BOUNDARY,BOUNDARY-60000),
            ("BTCUSDT","5m",1,BOUNDARY,BOUNDARY+31*86400000),
            ("BTCUSDT","5m",1,True,BOUNDARY+60000),
            ("BTCUSDT","5m",1,BOUNDARY,True),
        ):
            with self.subTest(args=args),self.assertRaises(ValueError):
                historical_asof_snapshot(
                    *args,reader=forbidden,now_ms=BOUNDARY+40*86400000)

    def test_missing_mixed_or_partial_never_backfill(self):
        rows=fixture_minutes(15,ingestion_ms=BOUNDARY)
        mixed=copy.deepcopy(rows)
        replacement=fixture_minutes(15,ingestion_ms=BOUNDARY)
        mixed[6]=replacement[6]
        for sample in (rows[:-1],mixed,rows[:8]+rows[9:]):
            with self.subTest(length=len(sample)),self.assertRaises(ProvenanceReadError):
                historical_asof_snapshot("BTCUSDT","5m",3,
                    BOUNDARY,BOUNDARY+60000,
                    reader=lambda *_:sample,now_ms=BOUNDARY+3600000)

    def test_historical_handler_managed_bearer_and_post_revoke(self):
        path=(HISTORICAL_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=3"+
              "&before_ms="+str(BOUNDARY)+"&as_of_ms="+str(BOUNDARY+60000))
        h=handler(path)
        with patch("market_data.history_api.immutable_minutes",
                   return_value=fixture_minutes(15,ingestion_ms=BOUNDARY)) as read:
            with patch("market_data_v2.read_api.time.time",
                       return_value=(BOUNDARY+3600000)/1000):
                h.do_GET()
        self.assertEqual(h.results[0][0],200)
        self.assertEqual(h.results[0][1]["reason"],"HISTORICAL_AS_OF_SOURCE_ONLY")
        self.assertEqual(h.server.startup_admission.calls,3)
        read.assert_called_once_with("BTCUSDT",15,BOUNDARY)

    def test_historical_invalid_http_never_reads(self):
        prefix=HISTORICAL_ROUTE+"?symbol=BTCUSDT&timeframe=5m&limit=1"
        for suffix in ("&before_ms="+str(BOUNDARY),
                       "&as_of_ms="+str(BOUNDARY),
                       "&before_ms=0&as_of_ms="+str(BOUNDARY+60000),
                       "&before_ms="+str(BOUNDARY+1)+
                       "&as_of_ms="+str(BOUNDARY+60000),
                       "&before_ms="+str(BOUNDARY)+
                       "&as_of_ms="+str(BOUNDARY+60000)+"&extra=yes"):
            h=handler(prefix+suffix)
            with patch("market_data.history_api.immutable_minutes",
                       side_effect=AssertionError("invalid attempted SQL")):
                h.do_GET()
            self.assertEqual(h.results[0][0],400)


if __name__=="__main__":
    unittest.main()
