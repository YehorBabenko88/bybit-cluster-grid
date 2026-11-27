"""Root-managed HTTP negative tests; no Bybit, SQL, trading or mutation."""
import asyncio
import copy
import json
import hashlib
import unittest
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import patch

from test_qualified_rollup_round27 import handler, Admission as HttpAdmission
from market_data_v2.read_api import (
    OBSERVED_UNIVERSE_ROUTE, INSTRUMENT_UNIVERSE_ROUTE,
)
from market_data_v2.exchange_roster_epoch import (
    observe_linear_roster, freeze_observation_for_root, RootStagedRoster)
from market_data_v2.instrument_universe import _sha
from market_data_v2 import read_api


class RootAdmission:
    def require_current(self):
        return True

    def current_roster_epoch(self):
        return "opaque-root-epoch"


class HttpEpochAdmission(HttpAdmission):
    def current_roster_epoch(self):
        return "opaque-root-epoch"


def staged_observation():
    row = dict(symbol="BTCUSDT", status="Trading",
               contractType="LinearPerpetual", settleCoin="USDT")
    p = SimpleNamespace(items=(row,), next_cursor=None,
                        completeness="INCOMPLETE",
                        response=SimpleNamespace(status=200, body_sha256="a"*64))
    async def fetch(base_url, *, cursor, limit):
        assert cursor is None and limit == 1000
        return p
    raw = asyncio.run(observe_linear_roster(
        "https://invalid.example", admission=RootAdmission(),
        lease_epoch="opaque-root-epoch", fetch_page=fetch,
        clock_ms=lambda: 1800000000000))
    return freeze_observation_for_root(
        raw, expected_lease_epoch="opaque-root-epoch",
        now_ms=1800000000000)


class ObservedRouteTests(unittest.TestCase):
    def setUp(self):
        self._clock = patch.object(read_api.time, "time", return_value=1800000000)
        self._clock.start()
        self.addCleanup(self._clock.stop)

    def test_root_managed_existing_listener_reads_only_staged_information(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        h.server.roster_observation = staged_observation()
        with patch("market_data.history_api.query",
                   side_effect=AssertionError("SQL not permitted")):
            with patch("market_data.history_api.immutable_minutes",
                       side_effect=AssertionError("candle reads forbidden")):
                h.do_GET()
        self.assertEqual(h.results[0][0], 200)
        result = h.results[0][1]
        self.assertEqual(result["status"], "INFORMATIONAL")
        self.assertEqual(result["records"][0]["symbol"], "BTCUSDT")
        self.assertFalse(result["delisting_authorized"])
        self.assertFalse(result["consumer_cutover_authorized"])
        self.assertFalse(result["trading_authorized"])
        self.assertEqual(h.server.startup_admission.calls, 3)

    def test_missing_staged_observation_is_503_and_discloses_no_rows(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        with patch("market_data.history_api.query",
                   side_effect=AssertionError("no SQL allowed")):
            h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertEqual(h.results[0][1]["error"], "UNIVERSE_SOURCE_UNQUALIFIED")
        self.assertNotIn("records", h.results[0][1])

    def test_http_cannot_supply_an_observation_or_query_parameters(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE + "?symbols=BTCUSDT", admission=HttpEpochAdmission())
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0][0], 400)
        self.assertNotIn("records", h.results[0][1])

    def test_unmanaged_and_bad_bearer_denied_without_source(self):
        for h in (handler(OBSERVED_UNIVERSE_ROUTE, identity=False, admission=HttpEpochAdmission()),
                  handler(OBSERVED_UNIVERSE_ROUTE, token=None, admission=HttpEpochAdmission()),
                  handler(OBSERVED_UNIVERSE_ROUTE, token="x"*64, admission=HttpEpochAdmission())):
            with self.subTest(path=h.path):
                h.server.roster_observation = staged_observation()
                h.do_GET()
                self.assertIn(h.results[0][0], (401, 503))
                self.assertNotIn("records", h.results[0][1])

    def test_post_read_lease_revocation_drops_entire_observation(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE,
                    admission=HttpEpochAdmission((True, True, False)))
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0], (503, {"error": "CURRENT_ADMISSION_REQUIRED"}))

    def test_rehashed_forged_delisting_flag_is_still_rejected(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        frozen = staged_observation()
        row = json.loads(frozen.payload_json)
        row["delisting_authorized"] = True
        row["dataset_fingerprint"] = _sha({
            k: v for k, v in row.items() if k != "dataset_fingerprint"})
        forged = json.dumps(row, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True).encode("ascii")
        h.server.roster_observation = replace(
            frozen, payload_json=forged,
            payload_sha256=hashlib.sha256(forged).hexdigest())
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_root_epoch_method_absent_fails_closed(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpAdmission())
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_root_epoch_mismatch_fails_closed(self):
        class ChangedEpoch(HttpEpochAdmission):
            def current_roster_epoch(self):
                return "new-epoch"
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=ChangedEpoch())
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_unfrozen_dict_staged_source_is_denied(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        raw = json.loads(staged_observation().payload_json)
        h.server.roster_observation = raw
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_staged_bytes_are_immutable(self):
        frozen = staged_observation()
        with self.assertRaises(FrozenInstanceError):
            frozen.payload_json = b"changed"
        self.assertIs(type(frozen.payload_json), bytes)

    def test_mutated_payload_digest_is_denied(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        frozen = staged_observation()
        h.server.roster_observation = replace(
            frozen, payload_json=frozen.payload_json + b" ")
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_replayed_staging_clock_is_denied(self):
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=HttpEpochAdmission())
        frozen = staged_observation()
        h.server.roster_observation = replace(frozen, captured_ms=1799999900000)
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertNotIn("records", h.results[0][1])

    def test_epoch_swaps_between_read_and_response_are_denied(self):
        class SwappingEpoch(HttpEpochAdmission):
            epoch_calls = 0
            def current_roster_epoch(self):
                self.epoch_calls += 1
                return "opaque-root-epoch" if self.epoch_calls == 1 else "new-root-epoch"
        h = handler(OBSERVED_UNIVERSE_ROUTE, admission=SwappingEpoch())
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0], (503, {"error": "CURRENT_ADMISSION_REQUIRED"}))
        self.assertEqual(h.server.startup_admission.calls, 3)

    def test_authoritative_route_remains_default_unavailable(self):
        h = handler(INSTRUMENT_UNIVERSE_ROUTE)
        h.server.roster_observation = staged_observation()
        h.do_GET()
        self.assertEqual(h.results[0][0], 503)
        self.assertEqual(h.results[0][1]["status"], "UNAVAILABLE")
        self.assertFalse(h.results[0][1]["consumer_cutover_authorized"])


if __name__ == "__main__":
    unittest.main()
