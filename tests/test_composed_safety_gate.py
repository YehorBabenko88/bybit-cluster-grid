"""Offline safety checks for composed Grid PR #174-178.

Checks fail closed when a required integration behavior is absent. This is a
source-level smoke gate, not a replacement for PostgreSQL/Windows/physical tests.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComposedSafetyGate(unittest.TestCase):
    def source(self, path):
        file = ROOT / path
        self.assertTrue(file.is_file(), f"required integration file missing: {path}")
        return file.read_text(encoding="utf-8")

    def test_wal_owner(self):
        self.source("grid/wal_directory_owner.py")
        source = self.source("grid/segment_wal.py")
        self.assertIn("wal_directory_owner", source)

    def test_independent_writer_fence(self):
        self.source("grid/job_write_fence.py")
        self.source("tests/test_raw_writer_fences_postgres.py")

    def test_evidence_capture_not_canonical(self):
        source = self.source("grid/micro_event_storage.py")
        self.assertIn("/ingest/capture", source)
        self.assertIn("QUARANTINED", source)
        self.source("tests/test_capture_sender_version_gate.py")

    def test_active_control_discovery(self):
        source = self.source("grid/micro_event_storage.py")
        self.assertIn("active_control", source)
        self.source("grid/active_control.py")
        self.source("tests/test_active_control_routing.py")

    def test_source_before_aggregation(self):
        self.source("tests/test_public_trade_capture.py")
        self.source("grid/collection_ownership.py")

    def test_migration_upgrade(self):
        self.source("tests/test_migration47_upgrade_postgres.py")
        self.source("tests/test_capture_evidence_postgres.py")

    def test_archive_fail_closed(self):
        self.source("tests/test_auxiliary_writer_lifecycle.py")
        self.source("grid/archive_service.py")

    def test_ci_keeps_both_branches_gates(self):
        preflight = self.source(".github/workflows/preflight.yml")
        windows = self.source(".github/workflows/windows-bundle.yml")
        for test in ("test_raw_writer_fences_postgres.py",
                     "test_capture_evidence_postgres.py",
                     "test_migration47_upgrade_postgres.py",
                     "test_wal_process_ownership.py"):
            self.assertIn(test, preflight, f"preflight dropped {test}")
        for test in ("test_wal_process_ownership.py",
                     "test_auxiliary_writer_lifecycle.py"):
            self.assertIn(test, windows, f"Windows matrix dropped {test}")


if __name__ == "__main__":
    unittest.main()
