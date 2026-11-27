"""Original inert Grid roster epoch tests; no network, DB or mutable registry."""
import copy
import unittest
from types import SimpleNamespace
from market_data_v2.exchange_roster_epoch import observe_linear_roster
from market_data_v2.instrument_universe import UniverseReadError, _sha


def page(rows, next_cursor=None):
    return SimpleNamespace(items=tuple(dict(symbol=s, status=state,
                                             contractType=kind, settleCoin=settle)
                                      for s, state, kind, settle in rows),
                           next_cursor=next_cursor, completeness="INCOMPLETE",
                           response=SimpleNamespace(status=200, body_sha256="a" * 64))


BTC = ("BTCUSDT", "Trading", "LinearPerpetual", "USDT")
ETH = ("ETHUSDT", "Trading", "LinearPerpetual", "USDT")
SOL = ("SOLUSDC", "PreLaunch", "LinearPerpetual", "USDC")


class Admission:
    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    def require_current(self):
        self.calls += 1
        return self.calls != self.fail_at


class EpochTests(unittest.IsolatedAsyncioTestCase):
    async def scan(self, groups, **overrides):
        calls = []
        async def transport(base_url, *, cursor, limit):
            calls.append((base_url, cursor, limit))
            return groups[len(calls) - 1]
        params = dict(admission=Admission(), lease_epoch="root-epoch-1",
                      fetch_page=transport, clock_ms=lambda: 1800000000000,
                      page_limit=2)
        params.update(overrides)
        return await observe_linear_roster("https://invalid.example", **params), calls

    async def test_two_complete_walks_informational_with_all_statuses(self):
        result, calls = await self.scan([page([BTC, ETH], "continuation"),
                                         page([SOL]), page([BTC, ETH], "continuation"),
                                         page([SOL])])
        self.assertEqual([x[1] for x in calls], [None, "continuation", None, "continuation"])
        self.assertEqual(result["record_count"], 3)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["cursor_walks_terminated"], 2)
        self.assertTrue(result["two_walk_roster_equal"])
        self.assertEqual(result["records"][2]["status"], "PreLaunch")
        self.assertEqual(result["status"], "INFORMATIONAL")
        self.assertEqual(result["exchange_completeness"], "NOT_ATTESTED")
        self.assertFalse(result["delisting_authorized"])
        self.assertFalse(result["consumer_cutover_authorized"])
        self.assertEqual(result["dataset_fingerprint"],
                         _sha({k: v for k, v in result.items() if k != "dataset_fingerprint"}))

    async def test_equal_count_replacement_is_epoch_drift(self):
        replacement = ("XRPUSDT", "Trading", "LinearPerpetual", "USDT")
        with self.assertRaisesRegex(UniverseReadError, "EPOCH_UNSTABLE"):
            await self.scan([page([BTC, ETH]), page([BTC, replacement])])

    async def test_status_only_change_is_epoch_drift(self):
        changed = ("BTCUSDT", "Retired", "LinearPerpetual", "USDT")
        with self.assertRaisesRegex(UniverseReadError, "EPOCH_UNSTABLE"):
            await self.scan([page([BTC]), page([changed])])

    async def test_repeated_cursor_refused(self):
        with self.assertRaisesRegex(UniverseReadError, "CURSOR_CYCLE"):
            await self.scan([page([BTC], "same"), page([ETH], "same")])

    async def test_duplicate_across_pages_refused(self):
        with self.assertRaisesRegex(UniverseReadError, "DUPLICATE_SYMBOL"):
            await self.scan([page([BTC], "next"), page([BTC])])

    async def test_empty_page_fails_closed(self):
        with self.assertRaisesRegex(UniverseReadError, "PAGE_PROVENANCE"):
            await self.scan([page([])])

    async def test_exhausted_page_budget_refused(self):
        with self.assertRaisesRegex(UniverseReadError, "PAGE_LIMIT"):
            await self.scan([page([BTC], "next")], max_pages=1)

    async def test_symbol_limit_refused(self):
        with self.assertRaisesRegex(UniverseReadError, "SYMBOL_LIMIT"):
            await self.scan([page([BTC, ETH])], max_symbols=1)

    async def test_postread_lease_revocation_refused(self):
        with self.assertRaisesRegex(UniverseReadError, "LEASE_REVOKED"):
            await self.scan([page([BTC])], admission=Admission(fail_at=3))

    async def test_missing_root_admission_no_transport(self):
        with self.assertRaisesRegex(UniverseReadError, "ROOT_ADMISSION_REQUIRED"):
            await self.scan([page([BTC])], admission=None)

    async def test_invalid_epoch_no_transport(self):
        with self.assertRaisesRegex(UniverseReadError, "EPOCH_REQUIRED"):
            await self.scan([page([BTC])], lease_epoch="")

    async def test_malformed_contract_refused(self):
        broken = ("BTCUSDT", "Trading", "", "USDT")
        with self.assertRaisesRegex(UniverseReadError, "RECORD_FIELDS"):
            await self.scan([page([broken])])

    async def test_opaque_cursor_byte_budget(self):
        with self.assertRaisesRegex(UniverseReadError, "CURSOR_INVALID"):
            await self.scan([page([BTC], "x" * 4097)])

    async def test_source_transport_error_sanitized(self):
        async def failing(*args, **kwargs):
            raise RuntimeError("confidential URL/token details")
        with self.assertRaisesRegex(UniverseReadError, "SOURCE_UNAVAILABLE"):
            await observe_linear_roster("https://invalid.example", admission=Admission(),
                                        lease_epoch="epoch", fetch_page=failing,
                                        clock_ms=lambda: 1800000000000)

    async def test_bogus_source_digest_fails(self):
        broken = page([BTC])
        broken.response.body_sha256 = "invalid"
        with self.assertRaisesRegex(UniverseReadError, "PAGE_PROVENANCE"):
            await self.scan([broken])


if __name__ == "__main__":
    unittest.main()
