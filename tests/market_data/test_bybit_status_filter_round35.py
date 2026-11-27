"""Original Grid transport status-segmentation tests, no actual network or trades.

Default path must remain unchanged for existing linear_symbols() consumer.
Explicit Bybit status is an informational filter, NOT exhaustive attestation.
"""
import json
import unittest
from unittest.mock import patch
from market_data.bybit import fetch_linear_instruments_page, _LINEAR_STATUS_QUERY

class Content:
    def __init__(self, data):
        self._chunks = [data, b""]
    async def read(self, limit):
        chunk = self._chunks.pop(0)
        if len(chunk) > limit:
            raise AssertionError("unexpected response limit")
        return chunk

class Response:
    status = 200
    headers = {"Content-Encoding": "identity"}
    def __init__(self, returned_status="Trading"):
        data = {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "status": returned_status,
             "contractType": "LinearPerpetual", "settleCoin": "USDT"}
        ], "nextPageCursor": ""}}
        self.content = Content(json.dumps(data).encode("utf-8"))
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    def raise_for_status(self):
        pass

class Session:
    def __init__(self, returned_status=None):
        self.calls = []
        self.returned_status = returned_status
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.returned_status or
                        kwargs["params"].get("status", "Trading"))

class BybitStatusFilterRound35(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, **kwargs):
        session = Session()
        with patch("market_data.bybit.aiohttp.ClientSession", return_value=session):
            page = await fetch_linear_instruments_page(
                "https://api.bybit.com", **kwargs)
        self.assertEqual(page.completeness, "INCOMPLETE")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][0],
                         "https://api.bybit.com/v5/market/instruments-info")
        self.assertIs(page.next_cursor, None)
        return session.calls[0][1]["params"]

    async def test_legacy_default_does_not_change_query(self):
        params = await self.fetch()
        self.assertEqual(params, {"category": "linear", "limit": 1000})

    async def test_each_official_status_uses_same_single_transport(self):
        self.assertEqual(_LINEAR_STATUS_QUERY,
                         frozenset({"PreLaunch", "PendingOpen", "Trading",
                                    "Delivering", "Closed"}))
        for state in sorted(_LINEAR_STATUS_QUERY):
            with self.subTest(status=state):
                params = await self.fetch(status=state, cursor="p.1", limit=10)
                self.assertEqual(params, {"category": "linear", "limit": 10,
                                          "cursor": "p.1", "status": state})

    async def test_invalid_status_rejected_before_http_client(self):
        for status in ("All", "Retired", "trading", "", "Trading ", 42,
                       True, ["Trading"], {"Trading": True}):
            with self.subTest(status=repr(status)):
                with patch("market_data.bybit.aiohttp.ClientSession",
                           side_effect=AssertionError("network created")):
                    with self.assertRaises(ValueError):
                        await fetch_linear_instruments_page(
                            "https://api.bybit.com", status=status)

    async def test_status_cannot_override_cursor_bounds(self):
        with patch("market_data.bybit.aiohttp.ClientSession",
                   side_effect=AssertionError("network created")):
            with self.assertRaises(ValueError):
                await fetch_linear_instruments_page(
                    "https://api.bybit.com", status="PreLaunch",
                    cursor="x" * 4097)

    async def test_misclassified_status_is_refused_not_silently_assumed(self):
        session = Session(returned_status="Trading")
        with patch("market_data.bybit.aiohttp.ClientSession", return_value=session):
            with self.assertRaisesRegex(ValueError, "status query mismatch"):
                await fetch_linear_instruments_page(
                    "https://api.bybit.com", status="PreLaunch")
        self.assertEqual(len(session.calls), 1)

    async def test_status_filter_never_claims_complete_source(self):
        params = await self.fetch(status="PreLaunch")
        self.assertEqual(params["status"], "PreLaunch")
        self.assertNotIn("complete", params)
        self.assertNotIn("exchange_completeness", params)

if __name__ == "__main__":
    unittest.main()
