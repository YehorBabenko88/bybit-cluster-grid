"""H R35 independent, byte-pinned B311 observational exchange-roster acceptance.

Loads the ORIGINAL B311 modules under an isolated test-only package.
No actual exchange requests, no DB, no alternative Bybit client and no delisting.
Even two consistent passes may NEVER grant external source authenticity.
"""
import copy
from hashlib import sha1
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / ".source" / "grid-b311" / "market_data_v2"
UNIVERSE = UPSTREAM / "instrument_universe.py"
EPOCH = UPSTREAM / "exchange_roster_epoch.py"
UNIVERSE_BLOB = "d05cb998c71cf4b5c0076eb2bec060bedb478767"
EPOCH_BLOB = "d05861cfdbcf8a64efcba29f7e565e7db5f75bd8"
BTC = ("BTCUSDT", "Trading", "LinearPerpetual", "USDT")
ETH = ("ETHUSDT", "Trading", "LinearPerpetual", "USDT")
XRP = ("XRPUSDT", "Trading", "LinearPerpetual", "USDT")


def git_blob(path, expected):
    data = path.read_bytes()
    actual = sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != expected:
        raise AssertionError("H_B311_ORIGINAL_BLOB_MISMATCH:" + path.name)
    return data


def original_b311():
    # Separate module objects: this test never replaces or imports the installed
    # canonical Grid module under its production name.
    git_blob(UNIVERSE, UNIVERSE_BLOB)
    git_blob(EPOCH, EPOCH_BLOB)
    package = types.ModuleType("h_b311_original")
    package.__path__ = [str(UPSTREAM)]
    with patch.dict(sys.modules, {"h_b311_original": package}):
        modules = {}
        for suffix, file in (("instrument_universe", UNIVERSE),
                             ("exchange_roster_epoch", EPOCH)):
            name = "h_b311_original." + suffix
            spec = importlib.util.spec_from_file_location(name, file)
            if spec is None or spec.loader is None:
                raise AssertionError("H_B311_ORIGINAL_IMPORT_MISSING")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[suffix] = module
        # Both source modules are immutable and kept under a distinct namespace.
        return modules["exchange_roster_epoch"], modules["instrument_universe"]


def page(rows, cursor=None, *, digest="a" * 64):
    return SimpleNamespace(
        items=[dict(symbol=s, status=state, contractType=kind, settleCoin=settle)
               for s, state, kind, settle in rows],
        next_cursor=cursor, completeness="INCOMPLETE",
        response=SimpleNamespace(status=200, body_sha256=digest))


class Admission:
    def __init__(self, revoke_at=None):
        self.calls = 0
        self.revoke_at = revoke_at

    def require_current(self):
        self.calls += 1
        return self.calls != self.revoke_at


class B311OriginalEpochIndependent(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.universe = original_b311()

    async def scan(self, pages, **overrides):
        calls = []
        async def transport(url, *, cursor, limit):
            calls.append((cursor, limit))
            return copy.deepcopy(pages[len(calls) - 1])
        options = dict(admission=Admission(), lease_epoch="h-isolated-epoch",
                       fetch_page=transport, clock_ms=lambda: 1800000000000,
                       page_limit=2)
        options.update(overrides)
        return await self.original.observe_linear_roster(
            "https://invalid.example", **options), calls

    async def test_two_walks_are_never_authority_even_with_matching_roster(self):
        result, calls = await self.scan([page([BTC], "next"),
                                         page([ETH]), page([BTC], "next"),
                                         page([ETH])])
        self.assertEqual(calls, [(None, 2), ("next", 2)] * 2)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["status"], "INFORMATIONAL")
        self.assertEqual(result["exchange_completeness"], "NOT_ATTESTED")
        self.assertEqual(result["lease_epoch_authenticity"],
                         "NOT_INDEPENDENTLY_ATTESTED")
        self.assertFalse(result["delisting_authorized"])
        self.assertFalse(result["consumer_cutover_authorized"])
        self.assertFalse(result["execution_authority"])
        self.assertFalse(result["paper_admitted"])
        self.assertEqual(result["dataset_fingerprint"], self.universe._sha({
            k: v for k, v in result.items() if k != "dataset_fingerprint"}))

    async def test_equal_cardinality_different_symbol_refused(self):
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_EPOCH_UNSTABLE"):
            await self.scan([page([BTC, ETH]), page([BTC, XRP])])

    async def test_changed_status_is_epoch_drift(self):
        retired = ("BTCUSDT", "Retired", "LinearPerpetual", "USDT")
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_EPOCH_UNSTABLE"):
            await self.scan([page([BTC]), page([retired])])

    async def test_duplicate_symbol_in_second_page_refused(self):
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_DUPLICATE_SYMBOL"):
            await self.scan([page([BTC], "next"), page([BTC])])

    async def test_repeated_cursor_refused_before_more_fetches(self):
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_CURSOR_CYCLE"):
            await self.scan([page([BTC], "next"), page([ETH], "next")])

    async def test_revocation_between_fetch_and_readback_refused(self):
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_LEASE_REVOKED"):
            await self.scan([page([BTC]), page([BTC])],
                            admission=Admission(revoke_at=3))

    async def test_forged_digest_or_missing_root_refused(self):
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_PAGE_PROVENANCE"):
            await self.scan([page([BTC], digest="not-sha")])
        with self.assertRaisesRegex(self.universe.UniverseReadError,
                                    "GRID_ROSTER_ROOT_ADMISSION_REQUIRED"):
            await self.scan([page([BTC])], admission=None)


if __name__ == "__main__":
    unittest.main()
