"""Regression tests for release supervisor rollback and confirmation guards."""
import pathlib
import os
import subprocess
import sys
import tempfile
import unittest

from grid import release_supervisor as supervisor


class ReleaseSupervisorTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows named mutex test")
    def test_second_supervisor_cannot_launch_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            child = root / "child.py"
            child.write_text("import time; time.sleep(30)", encoding="utf-8")
            cmd = [
                sys.executable, "-m", "grid.release_supervisor",
                "--install-root", str(root), "--version", "a" * 40,
                "--cwd", str(root), "--readiness", "worker",
                "--", sys.executable, str(child),
            ]
            with supervisor._single_instance(root, "worker"):
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("already running", result.stderr)
            self.assertFalse((root / "release-ready.txt").exists())

    def test_three_crashes_roll_back_and_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            (root / "previous.version").write_text(old)
            (root / "current.version").write_text(new)
            (root / "pending.version").write_text(new)
            old_release = root / "releases" / old
            old_release.mkdir(parents=True)
            (old_release / "run_worker.py").write_text("# fixture")
            self.assertFalse(supervisor._after_exit(root, new, 1))
            self.assertFalse(supervisor._after_exit(root, new, 1))
            self.assertTrue(supervisor._after_exit(root, new, 1))
            self.assertEqual((root / "current.version").read_text(), old)
            self.assertEqual((root / "failed.version").read_text(), new)
            self.assertFalse((root / "pending.version").exists())

    def test_no_rollback_to_missing_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            new = "b" * 40
            (root / "pending.version").write_text(new)
            (root / "previous.version").write_text("a" * 40)
            for _ in range(3):
                self.assertFalse(supervisor._after_exit(root, new, 1))
            self.assertTrue((root / "pending.version").exists())
            self.assertFalse((root / "failed.version").exists())

    def test_unresolved_journal_blocks_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            (root / "previous.version").write_text(old)
            (root / "current.version").write_text(new)
            (root / "pending.version").write_text(new)
            (root / "switch-journal.json").write_text('{"phase":"committed"}')
            previous = root / "releases" / old
            previous.mkdir(parents=True)
            (previous / "run_worker.py").write_text("# fixture")
            for _ in range(4):
                self.assertFalse(supervisor._after_exit(root, new, 1))
            self.assertEqual((root / "current.version").read_text(), new)
            self.assertFalse((root / "pending-crashes.txt").exists())

    def test_mismatched_current_blocks_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            (root / "previous.version").write_text(old)
            (root / "current.version").write_text(old)
            (root / "pending.version").write_text(new)
            previous = root / "releases" / old
            previous.mkdir(parents=True)
            (previous / "run_worker.py").write_text("# fixture")
            self.assertFalse(supervisor._after_exit(root, new, 1))
            self.assertFalse((root / "pending-crashes.txt").exists())

    def test_other_version_exit_does_not_change_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "pending.version").write_text("b" * 40)
            self.assertFalse(supervisor._after_exit(root, "a" * 40, 1))
            self.assertFalse((root / "pending-crashes.txt").exists())


if __name__ == "__main__":
    unittest.main()
