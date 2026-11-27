"""H ROUND34: original D129 68-line MTF vs canonical B308 5m/15m differential.

The baseline is the ORIGINAL D129 function AST plus its ORIGINAL D167 Math.
Neither historical implementation is recopied, edited, or reimplemented.
Test-only external checkouts are pinned and byte-verified before execution.
No provider access, SQL, network, trading or other stateful side effects.
Passing synthetic stored 1m parity DOES NOT authorize G012 retirement.
"""
import ast
import copy
from decimal import Decimal
from hashlib import sha1
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from market_data.provenance import digest
from market_data_v2.read_api import qualified_rollup_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError

from h_mtf_fixture import BOUNDARY, NOW, minutes


ROOT = Path(__file__).resolve().parents[2]
OLD_D = ROOT / ".source" / "terminan-d129" / "terminan" / "qualified_partial.py"
OLD_MATH = ROOT / ".source" / "math-d167" / "python" / "market_math.py"
OLD_D_BLOB = "27cd754b97a0a8c32b0ec51daac41110dca35292"
OLD_MATH_BLOB = "aebe6f799ffe2c20c9b68daad10b96764c245246"


def _original_blob(path, expected):
    raw = path.read_bytes()
    oid = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if oid != expected:
        raise AssertionError("ORIGINAL_G012_GIT_BLOB_MISMATCH: " + path.name)
    return raw


def _original_d129():
    source = _original_blob(OLD_D, OLD_D_BLOB).decode("utf-8")
    _original_blob(OLD_MATH, OLD_MATH_BLOB)
    module = ast.parse(source, filename=str(OLD_D))
    function = [node for node in module.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "qualified_timeframe_rows"]
    if len(function) != 1:
        raise AssertionError("G012_ORIGINAL_68_LINE_SYMBOL_MISSING")
    constants = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {
                "_MTF_WINDOWS", "_MTF_MAX_SOURCE_ROWS", "_MTF_MAX_BARS"
            }:
                constants[target.id] = ast.literal_eval(node.value)
    if set(constants) != {
        "_MTF_WINDOWS", "_MTF_MAX_SOURCE_ROWS", "_MTF_MAX_BARS"
    }:
        raise AssertionError("G012_ORIGINAL_SOURCE_CONSTANTS_MISSING")
    safe_env = {"__builtins__": __builtins__, **constants}
    exec(compile(ast.Module(body=function, type_ignores=[]), str(OLD_D),
                 "exec"), safe_env)
    spec = importlib.util.spec_from_file_location(
        "h_original_math_d167", OLD_MATH)
    if spec is None or spec.loader is None:
        raise AssertionError("G012_ORIGINAL_MATH_IMPORT_MISSING")
    historic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(historic)
    if not hasattr(historic, "aggregate_closed_minute_ohlcv"):
        raise AssertionError("G012_ORIGINAL_MATH_KERNEL_MISSING")
    return safe_env["qualified_timeframe_rows"], historic


def _legacy_receipt(rows):
    width = len(rows)
    return {
        "status": "PARTIAL", "chart_read_only": True,
        "execution_authority": False,
        "paper_admitted": False,
        "trading_authorized": False,
        "source_authenticity": "NOT_INDEPENDENTLY_ATTESTED",
        "record_integrity": "VERIFIED",
        "rows": tuple(copy.deepcopy(rows)),
        "coverage": {"expected_minutes": width,
                     "observed_minutes": width, "missing_minutes": 0},
        "dataset_fingerprint": digest(rows),
        "freshness_utc_ms": NOW,
    }


class HOriginalD129VsGridB308(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original, cls.historic_math = _original_d129()
        # Original is a module-level function; prevent unittest instance access
        # from injecting a spurious self positional argument (D's R35 failure).
        cls.original = staticmethod(original)

    def _old(self, rows, timeframe, count):
        # Scoped injection only into original 68-line historical source,
        # never into canonical Grid or production Math code.
        with patch.dict(sys.modules, {"market_math": self.historic_math}):
            return self.original(_legacy_receipt(rows), timeframe,
                                 max_bars=count)

    def test_same_input_ohlcv_volume_closed_clock_and_non_authority(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            for count in (1, 2):
                for buy, sell in ((0.1, 0.3), (1.0, 0.5)):
                    with self.subTest(timeframe=timeframe, count=count,
                                      buy=buy, sell=sell):
                        rows = minutes(width * count, buy=buy, sell=sell)
                        current = qualified_rollup_snapshot(
                            "BTCUSDT", timeframe, count, before_ms=BOUNDARY,
                            reader=lambda *_: copy.deepcopy(rows),
                            now_ms=NOW, exact=True)
                        legacy = self._old(rows, timeframe, count)
                        self.assertEqual(legacy["status"], current["status"])
                        self.assertEqual(legacy["source_minutes"],
                                         current["source_minutes"])
                        self.assertEqual(len(legacy["rows"]), len(current["rows"]))
                        self.assertEqual(legacy["coverage"], current["coverage"])
                        for earlier, newer in zip(legacy["rows"], current["rows"]):
                            for old, new in (("o", "open"), ("h", "high"),
                                             ("l", "low"), ("c", "close")):
                                self.assertEqual(Decimal(earlier[old]),
                                                 Decimal(str(newer[new])))
                            self.assertEqual(Decimal(earlier["v"]),
                                             Decimal(newer["volume_decimal"]))
                            self.assertEqual(earlier["t"], newer["start_ms"])
                            self.assertEqual(earlier["closed_at_ms"],
                                             newer["end_ms"] + 1)
                        for key in ("paper_admitted", "execution_authority",
                                    "trading_authorized"):
                            self.assertIs(legacy[key], False)
                            self.assertIs(current[key], False)
                        self.assertEqual(
                            legacy["source_authenticity"],
                            current["source_authenticity"])
                        self.assertEqual(current["api_version"],
                                         {"major": 2, "minor": 1})
                        self.assertEqual(current["source_numeric_precision"],
                                         "STORED_1M_JSON_NUMBERS_NOT_PROVIDER_RAW")

    def test_original_and_canonical_reject_missing_interior_minute(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            rows = minutes(width, buy=1.0, sell=0.5)
            broken = rows[:2] + rows[3:]
            with self.subTest(timeframe=timeframe):
                with self.assertRaises(ValueError):
                    self._old(broken, timeframe, 1)
                with self.assertRaises(ProvenanceReadError):
                    qualified_rollup_snapshot(
                        "BTCUSDT", timeframe, 1, before_ms=BOUNDARY,
                        reader=lambda *_: copy.deepcopy(broken),
                        now_ms=NOW, exact=True)

    def test_both_paths_refuse_duplicate_or_shifted_minute_without_mutation(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            original = minutes(width, buy=1.0, sell=0.5)
            for mode in ("duplicate", "shifted"):
                damaged = copy.deepcopy(original)
                if mode == "duplicate":
                    damaged[2] = copy.deepcopy(damaged[1])
                else:
                    damaged[2]["start_ms"] += 60000
                pristine = copy.deepcopy(damaged)
                with self.subTest(timeframe=timeframe, mutation=mode):
                    with self.assertRaises(ValueError):
                        self._old(damaged, timeframe, 1)
                    with self.assertRaises(ProvenanceReadError):
                        qualified_rollup_snapshot(
                            "BTCUSDT", timeframe, 1, before_ms=BOUNDARY,
                            reader=lambda *_: copy.deepcopy(damaged),
                            now_ms=NOW, exact=True)
                    self.assertEqual(damaged, pristine)
                    self.assertEqual(original, minutes(width, buy=1.0, sell=0.5))

    def test_original_and_canonical_deny_incomplete_full_bar(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            rows = minutes(width, buy=1.0, sell=0.5)[:-1]
            with self.subTest(timeframe=timeframe):
                with self.assertRaises(ValueError):
                    self._old(rows, timeframe, 1)
                with self.assertRaises(ProvenanceReadError):
                    qualified_rollup_snapshot(
                        "BTCUSDT", timeframe, 1, before_ms=BOUNDARY,
                        reader=lambda *_: copy.deepcopy(rows),
                        now_ms=NOW, exact=True)

    def test_canonical_receipt_is_read_only_and_does_not_modify_source(self):
        for timeframe, width in (("5m", 5), ("15m", 15)):
            source_rows = minutes(width, buy=0.1, sell=0.3)
            preserved = copy.deepcopy(source_rows)
            with self.subTest(timeframe=timeframe):
                legacy = self._old(source_rows, timeframe, 1)
                current = qualified_rollup_snapshot(
                    "BTCUSDT", timeframe, 1, before_ms=BOUNDARY,
                    reader=lambda *_: copy.deepcopy(source_rows),
                    now_ms=NOW, exact=True)
                self.assertEqual(source_rows, preserved)
                for receipt in (legacy, current):
                    self.assertIs(receipt["read_only"], True)
                    self.assertIs(receipt["paper_admitted"], False)
                    self.assertIs(receipt["execution_authority"], False)
                    self.assertIs(receipt["trading_authorized"], False)
                    self.assertEqual(
                        receipt["source_authenticity"],
                        "NOT_INDEPENDENTLY_ATTESTED")

    def test_comparison_does_not_claim_source_trust_or_retirement(self):
        rows = minutes(5, buy=1.0, sell=0.5)
        current = qualified_rollup_snapshot(
            "BTCUSDT", "5m", 1, before_ms=BOUNDARY,
            reader=lambda *_: copy.deepcopy(rows), now_ms=NOW, exact=True)
        self.assertFalse(current["execution_authority"])
        self.assertFalse(current["trading_authorized"])
        self.assertFalse(current["paper_admitted"])
        self.assertFalse(current["immutable"])
        self.assertEqual(current["exchange_completeness"], "NOT_ATTESTED")
        self.assertEqual(current["source_authenticity"],
                         "NOT_INDEPENDENTLY_ATTESTED")


if __name__ == "__main__":
    unittest.main()
