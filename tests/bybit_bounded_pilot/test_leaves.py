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
        aiohttp.ClientResponseError = type("ClientResponseError", (RuntimeError,), {})
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

    def test_stale_backfill_recovery_only_updates_claim_metadata(self):
        class Pool:
            def __init__(self): self.calls = []
            async def execute(self, statement, *args):
                self.calls.append((statement, args))
                return "UPDATE 2"
        pool = Pool()
        result = complete(self.market_backfill.recover_stale_backfill_jobs(
            pool, stale_minutes=15, max_attempts=3))
        self.assertEqual(result, "UPDATE 2")
        self.assertEqual(len(pool.calls), 1)
        sql, args = pool.calls[0]
        self.assertEqual(args, (15, 3))
        self.assertIn("UPDATE market_backfill_state", sql)
        self.assertIn("status='running'", sql)
        self.assertIn("attempts<$2", sql)
        self.assertNotIn("DELETE", sql.upper())
        self.assertNotIn("ohlcv_1m", sql)
        self.assertNotIn("ON CONFLICT", sql)

    def test_stale_backfill_recovery_rejects_invalid_policy_before_db(self):
        class Pool:
            async def execute(self, *_args):
                raise AssertionError("invalid policy must not touch database")
        for minutes, attempts in ((0, 1), (1441, 1), (True, 1),
                                  (1, 0), (1, 101), (1, False),
                                  (1.5, 2), (1, "2")):
            with self.subTest(minutes=minutes, attempts=attempts):
                with self.assertRaises(ValueError):
                    complete(self.market_backfill.recover_stale_backfill_jobs(
                        Pool(), stale_minutes=minutes, max_attempts=attempts))

    def test_short_bybit_page_is_not_complete_without_exhaustion(self):
        """A one-row page must persist its cursor as queued, not mark complete."""
        from datetime import datetime, timezone

        class Pool:
            def __init__(self):
                self.calls = []

            async def execute(self, statement, *args):
                self.calls.append((statement, args))
                return "UPDATE 1"

        seen = []

        async def fetch(_url, symbol, interval, end_ms):
            seen.append((symbol, interval, end_ms))
            return [["120000", "1", "2", "1", "2", "3"]]

        async def store(_pool, symbol, rows):
            self.assertEqual(symbol, "BTCUSDT")
            self.assertEqual(len(rows), 1)
            stamp = datetime.fromtimestamp(120, timezone.utc)
            return stamp, stamp

        async def no_sleep(_seconds):
            return None

        self.market_backfill.fetch_kline_page = fetch
        self.market_backfill.store_kline_page = store
        self.market_backfill.asyncio.sleep = no_sleep
        pool = Pool()
        result = complete(self.market_backfill.backfill_symbol(
            pool, "https://example.invalid",
            {"symbol": "BTCUSDT", "timeframe": "1", "launch_time_ms": 0},
            max_pages=1, pause=0))
        self.assertFalse(result["complete"])
        self.assertEqual(result["pages"], 1)
        self.assertEqual(seen, [("BTCUSDT", "1", None)])
        self.assertEqual(len(pool.calls), 1)
        sql, args = pool.calls[0]
        self.assertIn("UPDATE market_backfill_state", sql)
        self.assertEqual(args[2], "queued")
        self.assertEqual(args[5], 119999)

    def test_meta_oi_public_page_preserves_decimal_and_order(self):
        # Independent Meta parse_oi equivalence: positive OI values sorted by
        # timestamp with Decimal significance; output is an unverified Grid page.
        self.response = Response(body=b'{"retCode":0,"result":{"list":['
            b'{"timestamp":"60000","openInterest":"1234567890123.12345678901234567890"},'
            b'{"timestamp":"30000","openInterest":"0.00000001"}]}}')
        rows = complete(self.market_backfill.fetch_open_interest_page(
            "https://example.invalid", "BTCUSDT", start_ms=0, end_ms=60000, limit=2))
        self.assertEqual(rows, [
            {"symbol":"BTCUSDT","timestamp_ms":30000,"open_interest":"1E-8"},
            {"symbol":"BTCUSDT","timestamp_ms":60000,
             "open_interest":"1234567890123.12345678901234567890"},
        ])
        self.assertEqual(self.requests[0][0],
                         "https://example.invalid/v5/market/open-interest")
        self.assertEqual(self.requests[0][1]["params"],
                         {"category":"linear","symbol":"BTCUSDT","intervalTime":"5min",
                          "limit":2,"startTime":0,"endTime":60000})
        self.assertFalse(self.requests[0][1]["allow_redirects"])
        self.assertFalse(self.sessions[0]["trust_env"])
        self.assertFalse(self.sessions[0]["auto_decompress"])

    def test_meta_oi_invalid_ranges_before_network(self):
        for kw in ({"start_ms":True}, {"end_ms":-1}, {"start_ms":2,"end_ms":1},
                   {"limit":0}, {"limit":201}, {"limit":True},
                   {"interval":"2m"}, {"symbol":"BTC/USDT"},
                   {"base_url":"http://example.invalid"}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                complete(self.market_backfill.fetch_open_interest_page(
                    kw.pop("base_url","https://example.invalid"),
                    kw.pop("symbol","BTCUSDT"), **kw))
        self.assertEqual(self.sessions, [])

    def test_meta_oi_invalid_records_fail_closed(self):
        for value in ('NaN', 'Infinity', '-1', 'not-a-decimal', ''):
            self.response = Response(body=(
                '{"retCode":0,"result":{"list":[{"timestamp":"1000",'
                '"openInterest":"' + value + '"}]}}').encode())
            with self.subTest(value=value),self.assertRaises(ValueError):
                complete(self.market_backfill.fetch_open_interest_page(
                    "https://example.invalid", "BTCUSDT"))
        for record in ('{"timestamp":true,"openInterest":"1"}',
                       '{"timestamp":0,"openInterest":"1"}',
                       '{"timestamp":"1000","openInterest":1}',
                       '{"timestamp":"1000"}'):
            self.response = Response(body=(
                '{"retCode":0,"result":{"list":[' + record + ']}}').encode())
            with self.subTest(record=record),self.assertRaises(ValueError):
                complete(self.market_backfill.fetch_open_interest_page(
                    "https://example.invalid", "BTCUSDT"))

    def test_meta_oi_overlimit_and_provider_refusal(self):
        self.response = Response(body=b'{"retCode":0,"result":{"list":['
            b'{"timestamp":"1000","openInterest":"1"},'
            b'{"timestamp":"2000","openInterest":"2"}]}}')
        with self.assertRaises(ValueError):
            complete(self.market_backfill.fetch_open_interest_page(
                "https://example.invalid", "BTCUSDT", limit=1))
        self.response = Response(body=b'{"retCode":10006,"result":{"list":[]}}')
        with self.assertRaises(ValueError):
            complete(self.market_backfill.fetch_open_interest_page(
                "https://example.invalid", "BTCUSDT"))

    def test_pinned_meta_parse_oi_same_input_parity(self):
        """Use exact source from Meta #81; no Meta client, PG or runtime startup."""
        import hashlib
        import json
        import os
        import subprocess
        root = os.environ.get("META_OI_SOURCE_DIR")
        if not root:
            self.skipTest("cross-repo Meta source checkout required")
        source_root = pathlib.Path(root)
        source_path = pathlib.Path("src/meta_analyse/open_interest.py")
        expected_head = "b49505da42a274f7232fabe5d847c91f7218a0ce"
        expected_blob = "e63c3480a20b5c9f0487d89e444955839ec8245e"
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(source_root), *args], stderr=subprocess.DEVNULL).strip()
        self.assertEqual(git("rev-parse", "HEAD").decode(), expected_head)
        self.assertEqual(git("rev-parse", "HEAD:" + source_path.as_posix()).decode(),
                         expected_blob)
        # Execute the validated raw Git object directly, not a checkout that
        # may contain a platform-specific filter or line-ending transformation.
        # HEAD and the exact blob OID were checked above; never trust unpinned
        # worktree bytes to define the original numerical reference.
        original = git("show", "HEAD:" + source_path.as_posix())
        alias = "_meta_oi_pinned_source_for_grid_parity"
        module = types.ModuleType(alias)
        module.__file__ = str(source_root / source_path)
        sys.modules[alias] = module
        try:
            exec(compile(original, module.__file__, "exec"), module.__dict__)
            source_rows = [
                {"timestamp":"60000","openInterest":"1234567890123.12345678901234567890"},
                {"timestamp":"30000","openInterest":"0.00000001"},
                {"timestamp":"45000","openInterest":"0"},
            ]
            reference = module.parse_oi("BTCUSDT", source_rows)
            self.response = Response(body=json.dumps(
                {"retCode":0,"result":{"list":source_rows}}).encode("utf-8"))
            actual = complete(self.market_backfill.fetch_open_interest_page(
                "https://example.invalid", "BTCUSDT", start_ms=0, end_ms=60000, limit=3))
            self.assertEqual(actual, [
                {"symbol":p.symbol,"timestamp_ms":p.timestamp_ms,
                 "open_interest":str(p.open_interest)} for p in reference])
        finally:
            sys.modules.pop(alias, None)

    def test_live_worker_discovery_uses_one_bounded_reader(self):
        """The existing Worker entrypoint must consume the canonical page reader."""
        self.response = Response(body=b'{"retCode":0,"result":{"list":['
            b'{"symbol":"BTCUSDT","status":"Trading","contractType":"LinearPerpetual",'
            b'"priceFilter":{"tickSize":"0.1"}}],"nextPageCursor":""}}')
        rows = complete(self.bybit.linear_symbols("https://example.invalid", max_attempts=1))
        self.assertEqual([x["symbol"] for x in rows], ["BTCUSDT"])
        self.assertEqual(len(self.requests), 1)
        self.assertGreater(len(self.response.reads), 0)
        self.assertFalse(self.requests[0][1]["allow_redirects"])
        self.assertFalse(self.sessions[0]["trust_env"])
        self.assertFalse(self.sessions[0]["auto_decompress"])
        self.assertEqual(self.sessions[0]["headers"]["Accept-Encoding"], "identity")

    def test_worker_discovery_rejects_invalid_bounded_page_before_registry(self):
        for payload in (b'not JSON', b'{"retCode":0,"result":{"list":[]}}',
                        b'{"retCode":0,"result":{"list":[],"nextPageCursor":""}}'):
            self.response = Response(body=payload)
            with self.subTest(payload=payload), self.assertRaises((ValueError,RuntimeError)):
                complete(self.bybit.linear_symbols("https://example.invalid", max_attempts=1))
        self.assertEqual(len(self.requests), 3)
