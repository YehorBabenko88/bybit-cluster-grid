"""Offline leaf tests: fake transport, no asyncio loop or SDK imports."""
import importlib.util
import pathlib
import sys
import types
import unittest


def complete(coroutine):
    try:
        yielded = coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError(f"unexpected suspension: {yielded!r}")


class Response:
    def __init__(self, body=b'{"retCode":0,"result":{"list":[],"nextPageCursor":"next"}}', status=200, encoding="identity"):
        self.body = body
        self.status = status
        self.headers = {"Content-Encoding": encoding}
        self.content = self
        self.reads = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def read(self, n):
        self.reads.append(n)
        result, self.body = self.body[:n], self.body[n:]
        return result

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self, **kwargs):
        raise AssertionError("unbounded response.json called")


class LeafTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.sessions = []
        self.response = Response()
        owner = self

        class Session:
            def __init__(self, **kwargs):
                owner.sessions.append(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def get(self, url, **kwargs):
                owner.requests.append((url, kwargs))
                return owner.response

        self.saved = {}
        aiohttp = types.ModuleType("aiohttp")
        aiohttp.ClientSession = Session
        aiohttp.ClientTimeout = lambda **kwargs: kwargs
        aiohttp.DummyCookieJar = lambda: None
        aiohttp.ClientError = RuntimeError
        asynchronous = types.ModuleType("asyncio")
        asynchronous.CancelledError = type("CancelledError", (BaseException,), {})
        asynchronous.TimeoutError = TimeoutError
        for name, value in (("aiohttp", aiohttp), ("asyncio", asynchronous)):
            self.saved[name] = sys.modules.get(name)
            sys.modules[name] = value
        self.modules = []
        root = pathlib.Path(__file__).resolve().parents[2]
        package_name = "_a3_bounded_test"
        if package_name in sys.modules:
            raise AssertionError("unexpected cached private package")
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package
        self.modules.append(package_name)
        for leaf in ("bybit", "market_backfill"):
            alias = package_name + "." + leaf
            if alias in sys.modules:
                raise AssertionError("unexpected cached private source module")
            spec = importlib.util.spec_from_file_location(alias, root / "grid" / (leaf + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[alias] = module
            self.modules.append(alias)
            spec.loader.exec_module(module)
            setattr(self, leaf, module)

    def tearDown(self):
        for name in self.modules:
            sys.modules.pop(name)
        for name, value in self.saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value

    def test_one_page_never_universe(self):
        page = complete(self.bybit.fetch_linear_instruments_page("https://example.invalid"))
        self.assertEqual(page.completeness, "INCOMPLETE")
        self.assertEqual(page.next_cursor, "next")
        self.assertEqual(page.items, ())
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][1]["params"], {"category": "linear", "limit": 1000})
        self.assertIsInstance(page.response.body, bytes)

    def test_cursor_forwarded_without_auto_pagination(self):
        complete(self.bybit.fetch_linear_instruments_page("https://example.invalid", cursor="one", limit=2))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][1]["params"]["cursor"], "one")

    def test_body_overflow_stops(self):
        self.response.body = b"12345"
        with self.assertRaises(ValueError):
            complete(self.bybit._read_bounded_http_response(self.response, max_body_bytes=4))
        self.assertTrue(all(0 < n <= 65536 for n in self.response.reads))

    def test_encoding_rejected(self):
        self.response.headers["Content-Encoding"] = "gzip"
        with self.assertRaises(ValueError):
            complete(self.bybit._read_bounded_http_response(self.response))

    def test_http_errors_do_not_retry(self):
        for status in (301, 302, 307, 308, 429, 403):
            with self.subTest(status=status):
                self.requests.clear()
                self.response = Response(status=status)
                with self.assertRaises((RuntimeError, ValueError)):
                    complete(self.bybit.fetch_linear_instruments_page("https://example.invalid"))
                self.assertEqual(len(self.requests), 1)

    def test_invalid_json_stops(self):
        self.response.body = b"not JSON"
        with self.assertRaises(ValueError):
            complete(self.bybit.fetch_linear_instruments_page("https://example.invalid"))
        self.assertEqual(len(self.requests), 1)

    def test_kline_exact_zero_bounds(self):
        self.response.body = b'{"retCode":0,"result":{"list":[]}}'
        self.assertEqual(complete(self.market_backfill.fetch_kline_page("https://example.invalid", "BTCUSDT", end_ms=0, limit=1, start_ms=0)), [])
        self.assertEqual(self.requests[0][1]["params"], {"category": "linear", "symbol": "BTCUSDT", "interval": "1", "limit": 1, "start": 0, "end": 0})
        self.assertFalse(self.requests[0][1]["allow_redirects"])
        self.assertFalse(self.sessions[0]["auto_decompress"])
        self.assertFalse(self.sessions[0]["trust_env"])

    def test_bad_bounds_rejected_before_session(self):
        for start, end, limit in ((True, 1, 1), (0.5, 1, 1), (2, 1, 1), (-1, 1, 1), (0, 1, True), (0, 1, 1001)):
            with self.subTest(start=start, end=end, limit=limit):
                with self.assertRaises((ValueError, TypeError)):
                    complete(self.market_backfill.fetch_kline_page("https://example.invalid", "BTCUSDT", end_ms=end, limit=limit, start_ms=start))
        self.assertEqual(self.sessions, [])

    def test_page_invalid_limit_before_session(self):
        for limit in (True, 0, 1001, 1.5):
            with self.assertRaises((ValueError, TypeError)):
                complete(self.bybit.fetch_linear_instruments_page("https://example.invalid", limit=limit))
        self.assertEqual(self.sessions, [])

    def test_backfill_without_start_uses_the_same_bounded_reader(self):
        self.response.body = b'{"retCode":0,"result":{"list":[["0","1","2","1","2","3"]]}}'
        rows = complete(self.market_backfill.fetch_kline_page(
            "https://example.invalid", "BTCUSDT", end_ms=0, limit=1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.requests[0][1]["params"],
                         {"category":"linear","symbol":"BTCUSDT","interval":"1","limit":1,"end":0})
        self.assertEqual(self.requests[0][0], "https://example.invalid/v5/market/kline")
        self.assertFalse(self.requests[0][1]["allow_redirects"])
        self.assertFalse(self.sessions[0]["trust_env"])
        self.assertFalse(self.sessions[0]["auto_decompress"])
        self.assertGreater(len(self.response.reads), 0)

    def test_backfill_without_start_rejects_invalid_inputs_before_io(self):
        cases = [
            ("http://example.invalid", "BTCUSDT", "1", None, 1, None),
            ("https://example.invalid/path", "BTCUSDT", "1", None, 1, None),
            ("https://example.invalid", "../BTC", "1", None, 1, None),
            ("https://example.invalid", "BTCUSDT", "1", True, 1, None),
            ("https://example.invalid", "BTCUSDT", "1", -1, 1, None),
            ("https://example.invalid", "BTCUSDT", "1", None, True, None),
            ("https://example.invalid", "BTCUSDT", "1", None, 1001, None),
            ("https://example.invalid", "BTCUSDT", "1", None, 1, 0),
        ]
        for url, symbol, interval, end, limit, start in cases:
            with self.subTest(url=url, symbol=symbol, end=end, limit=limit, start=start):
                with self.assertRaises(ValueError):
                    complete(self.market_backfill.fetch_kline_page(
                        url, symbol, interval, end, limit, start_ms=start))
        self.assertEqual(self.sessions, [])

    def test_backfill_without_start_rejects_oversized_or_exchange_error(self):
        self.response.body = b"x" * (1048576 + 1)
        with self.assertRaises(ValueError):
            complete(self.market_backfill.fetch_kline_page("https://example.invalid", "BTCUSDT"))
        self.assertTrue(self.response.reads)
        self.response = Response(body=b'{"retCode":10006,"result":{"list":[]}}')
        with self.assertRaises(ValueError):
            complete(self.market_backfill.fetch_kline_page("https://example.invalid", "BTCUSDT"))
        self.assertEqual(len(self.requests), 2)

    def test_unique_strattester_price_series_use_existing_grid_reader(self):
        # Strattester had separate public Bybit GET methods for these URLs.
        # Grid must use one bounded session and never manufacture OHLCV writes.
        routes = {
            "mark_price":"mark-price-kline",
            "index_price":"index-price-kline",
            "premium_index":"premium-index-price-kline",
        }
        for dataset, route in routes.items():
            self.response = Response(body=b'{"retCode":0,"result":{"list":[["0","1","2","1","2"]]}}')
            result = complete(self.market_backfill.fetch_kline_page(
                "https://example.invalid", "BTCUSDT", start_ms=0, end_ms=60000,
                limit=2, dataset=dataset))
            self.assertEqual(len(result), 1)
            self.assertEqual(self.requests[-1][0], "https://example.invalid/v5/market/" + route)
            self.assertEqual(self.requests[-1][1]["params"]["start"], 0)
            self.assertFalse(self.requests[-1][1]["allow_redirects"])
            self.assertFalse(self.sessions[-1]["trust_env"])
        self.assertEqual(len(self.requests), 3)

    def test_price_series_rejects_unknown_dataset_before_io(self):
        for dataset in ("funding", "open_interest", "", True, None, "candles/../../order"):
            with self.subTest(dataset=dataset), self.assertRaises(ValueError):
                complete(self.market_backfill.fetch_kline_page(
                    "https://example.invalid", "BTCUSDT", dataset=dataset))
        self.assertEqual(self.sessions, [])
