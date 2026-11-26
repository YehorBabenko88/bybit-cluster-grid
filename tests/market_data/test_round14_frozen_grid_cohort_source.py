"""ROUND14 source-only four-blob pin for B30's frozen executable Grid cohort.

This deliberately DOES NOT attest a built wheel, protected Root manifest,
installed package, runtime entrypoint, publisher identity, OS/PG ownership,
Consul, real Bybit completeness, or native write authorization. E/F own those
independent checks. These tests verify exact bytes in THIS Git checkout.
"""
import hashlib
from pathlib import Path
import unittest

SOURCE_ROOT = Path(__file__).resolve().parents[2]

# (exact Git blob SHA-1, SHA-256, byte count) from B30 on 2026-11-26.
FROZEN_RUNTIME = {
    "grid/canonical_lab_fenced_writer.py": (
        "8b93466a79fa234468a3cdc44106bd5e153e81c4",
        "0dc72314f11791c3899732bc461be5273b890e7fd96553e85590dc5a384e4300",
        8543,
    ),
    "grid/canonical_lab_continuous_collector.py": (
        "52ed338cb5e1e5641fd9cf9f401b280fc3500a9b",
        "c691b8cbeee2b4e3fa0df95f81381318a297736ea109513c1d50340a13ad8a01",
        19554,
    ),
    "grid/c_lab_journal_adapter.py": (
        "ab93c6d421c3d3f0232060f6ded7ac01bf8eeda0",
        "69bb02182e73bfe4d80f98fa8f1cec846d18334693aa8443eec88babb901f01a",
        6613,
    ),
    "grid/c_async_fenced_writer.py": (
        "98ed95029785413eb8fbc5687af39ff6bd0bf2cf",
        "f4aaa97ac94a9b6ca37bbb6d50bebe6538ab1f4548f6c9e35b8be7845f37028e",
        2273,
    ),
}


class Round14FrozenGridSourceCohort(unittest.TestCase):
    def test_exact_four_files_have_matching_size_sha256_and_git_blob(self):
        self.assertEqual(len(FROZEN_RUNTIME), 4)
        for relative, (expected_blob, expected_sha, expected_bytes) in (
                FROZEN_RUNTIME.items()):
            with self.subTest(path=relative):
                path = SOURCE_ROOT / relative
                self.assertTrue(path.is_file(), relative)
                raw = path.read_bytes()
                self.assertEqual(len(raw), expected_bytes)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha)
                git_input = (b"blob " + str(len(raw)).encode("ascii") +
                             b"\\0" + raw)
                self.assertEqual(
                    hashlib.sha1(git_input).hexdigest(), expected_blob)

    def test_only_legacy_adapter_defines_sql_call_to_c_fenced_insert(self):
        writer = (SOURCE_ROOT /
                  "grid/canonical_lab_fenced_writer.py").read_text(
                      encoding="utf-8")
        self.assertIn("SELECT public.lab_fenced_insert(", writer)
        self.assertIn("class CanonicalLabMinuteWriter", writer)
        for relative in (
                "grid/canonical_lab_continuous_collector.py",
                "grid/c_lab_journal_adapter.py",
                "grid/c_async_fenced_writer.py"):
            with self.subTest(path=relative):
                source = (SOURCE_ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("SELECT public.lab_fenced_insert(", source)
                self.assertNotIn("psycopg.connect(", source)

    def test_recovery_never_rebinds_old_collector_instance(self):
        source = (SOURCE_ROOT /
                  "grid/canonical_lab_continuous_collector.py").read_text(
                      encoding="utf-8")
        start = source.index("    async def reconcile_after_restart(")
        end = source.index("    async def recover_durable_pending(", start)
        implementation = source[start:end]
        self.assertIn("RECOVERY_REQUIRES_FRESH_ROOT_COHORT", implementation)
        self.assertNotIn("self.journal=", implementation)
        self.assertNotIn("self.writer_grant=", implementation)
        self.assertNotIn("self.authority=", implementation)


if __name__ == "__main__":
    unittest.main()
