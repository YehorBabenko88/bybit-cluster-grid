"""Source-executed inert Grid five-status roster regression; no network or SQL."""
import copy
import unittest
from types import SimpleNamespace
from market_data_v2.instrument_universe import UniverseReadError, _sha
from market_data_v2.roster_status_segments import (
    observe_linear_status_segments, _STATUSES)


def page(rows, next_cursor=None):
    return SimpleNamespace(items=tuple(dict(symbol=s, status=state,
                      contractType="LinearPerpetual", settleCoin="USDT")
                      for s, state in rows), next_cursor=next_cursor,
                      completeness="INCOMPLETE",
                      response=SimpleNamespace(status=200, body_sha256="a" * 64))


class Guard:
    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at
    def require_current(self):
        self.calls += 1
        return self.calls != self.fail_at


class StatusSegmentTests(unittest.IsolatedAsyncioTestCase):
    async def scan(self, callback=None, **options):
        calls = []
        counts = {s: 0 for s in _STATUSES}
        async def reader(base_url, *, status, cursor, limit):
            calls.append((status, cursor, limit))
            n = counts[status]
            counts[status] += 1
            if callback:
                return callback(status, cursor, n)
            return page([(status.upper()+"USDT", status)])
        args = dict(admission=Guard(), lease_epoch="opaque-root-epoch",
                    fetch_page=reader, clock_ms=lambda: 1800000000000,
                    page_limit=2)
        args.update(options)
        return await observe_linear_status_segments(
            "https://invalid.example", **args), calls

    async def test_all_five_statuses_rounds_source_only(self):
        result, calls = await self.scan()
        self.assertEqual(result["queried_statuses"], list(_STATUSES))
        self.assertEqual(len(calls), 20)
        self.assertEqual(result["record_count"], 5)
        self.assertEqual(result["status"], "INFORMATIONAL")
        self.assertEqual(result["exchange_completeness"], "NOT_ATTESTED")
        self.assertFalse(result["delisting_authorized"])
        self.assertFalse(result["consumer_cutover_authorized"])
        self.assertEqual(result["dataset_fingerprint"],
                         _sha({k:v for k,v in result.items()
                              if k != "dataset_fingerprint"}))

    async def test_empty_terminal_segment_is_not_missing_status(self):
        out, calls = await self.scan(lambda s,c,n:
                                    page([]) if s=="Closed" else page([(s.upper()+"USDT",s)]))
        self.assertEqual(out["record_count"], 4)
        self.assertEqual(out["status_evidence"][0]["record_count"], 0)
        self.assertEqual(len(calls), 20)

    async def test_nonterminal_empty_page_denied(self):
        with self.assertRaisesRegex(UniverseReadError,"PAGE_PROVENANCE"):
            await self.scan(lambda s,c,n: page([],"next"))

    async def test_per_status_cursor_cycle_denied(self):
        with self.assertRaisesRegex(UniverseReadError,"CURSOR_CYCLE"):
            await self.scan(lambda s,c,n: page([(s.upper()+"USDT",s)],"same"))

    async def test_wrong_status_from_transport_denied(self):
        with self.assertRaisesRegex(UniverseReadError,"STATUS_FILTER_MISMATCH"):
            await self.scan(lambda s,c,n: page([("BTCUSDT","Trading")]))

    async def test_paginated_status_exhausts_cursor_each_cycle(self):
        def source(status, cursor, call_index):
            if status == "Closed":
                return (page([("BTCUSDT", status)], "next") if cursor is None
                        else page([("ETHUSDT", status)]))
            return page([(status.upper()+"USDT", status)])
        result, calls = await self.scan(source)
        self.assertEqual(result["record_count"], 6)
        self.assertEqual(result["status_evidence"][0]["page_count"], 2)
        self.assertEqual(result["status_evidence"][0]["cursor_walks_terminated"], 4)
        self.assertEqual(len(calls), 24)
        self.assertEqual([cursor for status,cursor,_ in calls if status == "Closed"],
                         [None, "next"] * 4)

    async def test_cursor_chain_drift_across_cycles_denied(self):
        def source(status, cursor, n):
            if status == "Closed":
                return (page([("BTCUSDT",status)], "next-A" if n < 4 else "next-B")
                        if cursor is None else page([("ETHUSDT",status)]))
            return page([(status.upper()+"USDT", status)])
        with self.assertRaisesRegex(UniverseReadError,"CROSS_CYCLE_DRIFT"):
            await self.scan(source)

    async def test_cross_status_same_symbol_refused(self):
        with self.assertRaisesRegex(UniverseReadError,"CROSS_STATUS_DUPLICATE"):
            await self.scan(lambda s,c,n: page([("BTCUSDT",s)]))

    async def test_cross_cycle_drift_denied(self):
        with self.assertRaisesRegex(UniverseReadError,"CROSS_CYCLE_DRIFT"):
            await self.scan(lambda s,c,n: page([(("X" if n>=2 else "B")+s.upper()+"USDT",s)]))

    async def test_total_limit_refused(self):
        with self.assertRaisesRegex(UniverseReadError,"SEGMENT_TOTAL_LIMIT"):
            await self.scan(max_symbols=4)

    async def test_root_lease_revoked_refused(self):
        with self.assertRaisesRegex(UniverseReadError,"LEASE_REVOKED"):
            await self.scan(admission=Guard(fail_at=3))

    async def test_total_window_overflow_denied(self):
        counts = [0]
        def clock():
            counts[0]+=1
            return 1800000000000 if counts[0]<22 else 1800000600001
        with self.assertRaises(UniverseReadError):
            await self.scan(clock_ms=clock)


if __name__ == "__main__":
    unittest.main()
