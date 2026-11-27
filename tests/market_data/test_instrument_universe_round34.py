"""Inert fail-closed source-custody checks; no exchange, SQL or Root mutation."""
import copy
import unittest
from unittest.mock import patch
from test_qualified_rollup_round27 import handler, Admission
from market_data_v2.read_api import INSTRUMENT_UNIVERSE_ROUTE
from market_data_v2.instrument_universe import (
    UniverseReadError, _sha, unavailable_universe, qualified_universe_snapshot,
)


class InstrumentUniverseRound34Tests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            {"page_index": 0, "symbols": ["BTCUSDT", "ETHUSDT"], "page_sha256": _sha(["BTCUSDT", "ETHUSDT"])},
        ]
        self.receipt = {
            "schema": "market_data.instrument-universe-source.v1",
            "producer": "market_data", "venue": "Bybit", "market_type": "linear",
            "snapshot_id": "a" * 64, "source_revision": "b" * 40,
            "lease_epoch": "opaque-root-epoch", "observed_at_ms": 1800000000000,
            "page_count": 1, "complete_count": 2,
            "completeness": "EXHAUSTIVE_ATTESTED",
            "independent_source_attestation": True, "admitted_by_root": True,
        }

    def test_inert_unavailable_never_exposes_symbols(self):
        row = unavailable_universe()
        self.assertEqual(row["schema"], "market_data.instrument-universe-envelope.v1")
        self.assertEqual(row["status"], "UNAVAILABLE")
        self.assertEqual(row["symbols"], [])
        self.assertEqual(row["symbol_count"], 0)
        self.assertFalse(row["consumer_cutover_authorized"])
        self.assertFalse(row["execution_authority"])
        self.assertFalse(row["trading_authorized"])
        self.assertEqual(row["dataset_fingerprint"],
                         _sha({k: v for k, v in row.items() if k != "dataset_fingerprint"}))

    def test_untrusted_self_asserted_attestation_cannot_authorize_delist(self):
        # Even all apparently correct fields and a digest are NOT independent
        # evidence of an exhaustive exchange snapshot.
        with self.assertRaisesRegex(UniverseReadError, "INDEPENDENT_ROOT_ATTESTATION"):
            qualified_universe_snapshot(
                self.pages, observation_ms=1800000000000,
                source_receipt=self.receipt)

    def test_wrong_source_identity_fails_before_any_admission(self):
        for change in (
            lambda r: r.update(market_type="spot"),
            lambda r: r.update(complete_count=1),
            lambda r: r.update(page_count=2),
            lambda r: r.update(admitted_by_root=1),
            lambda r: r.update(snapshot_id="malformed"),
            lambda r: r.update(observed_at_ms=0),
            lambda r: r.update(unexpected="extra"),
        ):
            with self.subTest(change=repr(change)):
                receipt = copy.deepcopy(self.receipt)
                change(receipt)
                with self.assertRaises(UniverseReadError):
                    qualified_universe_snapshot(
                        self.pages, observation_ms=1800000000000,
                        source_receipt=receipt)

    def test_empty_and_unbounded_pages_refused(self):
        for pages in ([], tuple(), [None], [[1]], list(range(1001))):
            with self.subTest(size=len(pages)):
                with self.assertRaises(UniverseReadError):
                    qualified_universe_snapshot(
                        pages, observation_ms=1800000000000,
                        source_receipt=self.receipt)

    def test_strattester_cannot_treat_not_attested_as_authorized_snapshot(self):
        row = unavailable_universe()
        self.assertNotIn("snapshot_id", row)
        self.assertNotIn("lease_epoch", row)
        self.assertNotIn("source_revision", row)
        self.assertFalse(row["consumer_cutover_authorized"])
        self.assertEqual(row["source_authenticity"], "NOT_ATTESTED")
        self.assertEqual(row["exchange_completeness"], "NOT_ATTESTED")


    def test_root_managed_inert_universe_route_denies_without_sql(self):
        h = handler(INSTRUMENT_UNIVERSE_ROUTE)
        with patch("market_data.history_api.immutable_minutes",
                   side_effect=AssertionError("unexpected PostgreSQL read")):
            with patch("market_data.history_api.query",
                       side_effect=AssertionError("unexpected registry query")):
                h.do_GET()
        self.assertEqual(len(h.results), 1)
        self.assertEqual(h.results[0][0], 503)
        self.assertEqual(h.results[0][1], unavailable_universe())
        self.assertEqual(h.server.startup_admission.calls, 3)

    def test_universe_route_requires_root_identity_and_valid_bearer(self):
        for h in (handler(INSTRUMENT_UNIVERSE_ROUTE, identity=False),
                  handler(INSTRUMENT_UNIVERSE_ROUTE, token=None),
                  handler(INSTRUMENT_UNIVERSE_ROUTE, token="c" * 64)):
            with self.subTest(path=h.path):
                with patch("market_data.history_api.immutable_minutes",
                           side_effect=AssertionError("unmanaged PostgreSQL read")):
                    h.do_GET()
                self.assertIn(h.results[0][0], (401, 503))
                self.assertFalse(h.results[0][1].get("trading_authorized", False))

    def test_universe_route_rejects_query_and_postread_lease_revocation(self):
        query = handler(INSTRUMENT_UNIVERSE_ROUTE + "?symbol=BTCUSDT")
        with patch("market_data.history_api.immutable_minutes",
                   side_effect=AssertionError("query must not read SQL")):
            query.do_GET()
        self.assertEqual(query.results[0][0], 400)
        revoked = handler(INSTRUMENT_UNIVERSE_ROUTE,
                          admission=Admission((True, True, False)))
        revoked.do_GET()
        self.assertEqual(revoked.results[0][0], 503)
        self.assertEqual(revoked.results[0][1]["error"],
                         "CURRENT_ADMISSION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
