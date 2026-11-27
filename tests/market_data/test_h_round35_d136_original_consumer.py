"""H/R35 current immutable D consumer against Grid canonical 5m/15m DTO.

Historical D136 consumer from immutable Git object is executed unchanged.
Canonical Grid/Math own source and arithmetic. All data are fabricated stored
minute receipts; exchange completeness and trading authority stay untrusted.
No real SQL, exchange HTTP, user data, orders, or old-component deletion.
"""
import copy
from decimal import Decimal
from hashlib import sha1
from pathlib import Path
import subprocess
import types
import unittest

from market_data.provenance import digest
from market_data_v2.read_api import qualified_rollup_snapshot
from h_mtf_fixture import BOUNDARY, NOW, minutes


ROOT = Path(__file__).resolve().parents[2]
D_ROOT = ROOT / ".source" / "terminan-d136"
D_HEAD = "d71b29b194b40f32a2de8a4cfd0100041489fd94"
D_FILE = "terminan/qualified_rollup.py"
D_BLOB = "77c6855c52030d5d9b0e839e0c9245b947db41b5"


def original_d_consumer():
    current = subprocess.check_output(
        ["git", "-C", str(D_ROOT), "rev-parse", "HEAD"], text=True).strip()
    if current != D_HEAD:
        raise AssertionError("H_D136_HEAD_MISMATCH")
    raw = subprocess.check_output(
        ["git", "-C", str(D_ROOT), "show", "HEAD:" + D_FILE])
    oid = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if oid != D_BLOB:
        raise AssertionError("H_D136_GIT_BLOB_MISMATCH")
    original = types.ModuleType("h_original_d136_consumer")
    original.__file__ = str(D_ROOT / D_FILE)
    exec(compile(raw.decode("utf-8"), original.__file__, "exec"),
         original.__dict__)
    return original


class HActualD136ConsumerParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = original_d_consumer()

    def envelope(self, frame, count=1):
        width = (5 if frame == "5m" else 15) * count
        rows = minutes(width, buy=0.1, sell=0.3)
        prior = copy.deepcopy(rows)
        env = qualified_rollup_snapshot(
            "BTCUSDT", frame, count, before_ms=BOUNDARY,
            reader=lambda *_: copy.deepcopy(rows), now_ms=NOW, exact=True)
        self.assertEqual(rows, prior)
        return env

    def test_original_d_admits_only_display_rows_after_grid_qualification(self):
        for frame in ("5m", "15m"):
            for count in (1, 2):
                with self.subTest(frame=frame, count=count):
                    env = self.envelope(frame, count)
                    received = self.d.validate_qualified_rollup(
                        env, "BTCUSDT", frame, count,
                        now_ms=NOW, exact=True)
                    displayed = self.d.chart_rollup_rows(received)
                    self.assertEqual(len(displayed), count)
                    for source, chart in zip(env["rows"], displayed):
                        self.assertEqual(chart["t"], source["start_ms"])
                        self.assertEqual(chart["closed_at_ms"],
                                         source["end_ms"] + 1)
                        self.assertEqual(Decimal(chart["v"]),
                                         Decimal(source["volume_decimal"]))
                        self.assertEqual(Decimal(chart["delta_decimal"]),
                                         Decimal(source["delta_decimal"]))
                    self.assertIs(env["paper_admitted"], False)
                    self.assertIs(env["execution_authority"], False)
                    self.assertIs(env["trading_authorized"], False)
                    self.assertEqual(env["exchange_completeness"], "NOT_ATTESTED")

    def test_rehashed_authority_forgery_is_rejected_by_original_d(self):
        env = self.envelope("5m")
        for name in ("paper_admitted", "execution_authority",
                     "trading_authorized"):
            altered = copy.deepcopy(env)
            altered[name] = True
            altered["dataset_fingerprint"] = digest({
                k: v for k, v in altered.items()
                if k != "dataset_fingerprint"})
            with self.subTest(flag=name), self.assertRaisesRegex(
                    ValueError, "QUALIFIED_ROLLUP_UNAVAILABLE"):
                self.d.validate_qualified_rollup(
                    altered, "BTCUSDT", "5m", 1, now_ms=NOW, exact=True)

    def test_rehashed_invalid_negative_zero_delta_is_rejected(self):
        env = self.envelope("5m")
        env["rows"][0]["delta_decimal"] = "-0"
        env["dataset_fingerprint"] = digest({
            k: v for k, v in env.items() if k != "dataset_fingerprint"})
        with self.assertRaisesRegex(ValueError, "QUALIFIED_ROLLUP_UNAVAILABLE"):
            self.d.validate_qualified_rollup(
                env, "BTCUSDT", "5m", 1, now_ms=NOW, exact=True)

    def test_live_receipt_cannot_downgrade_to_historical_asof(self):
        env = self.envelope("15m")
        with self.assertRaisesRegex(ValueError, "QUALIFIED_ROLLUP_UNAVAILABLE"):
            self.d.validate_qualified_rollup(
                env, "BTCUSDT", "15m", 1,
                now_ms=NOW, historical=True,
                before_ms=BOUNDARY, as_of_ms=BOUNDARY, exact=True)


if __name__ == "__main__":
    unittest.main()
