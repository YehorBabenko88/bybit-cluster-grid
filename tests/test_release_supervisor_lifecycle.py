"""Regression tests for release supervisor rollback and confirmation guards."""
import pathlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from grid import release_supervisor as supervisor


class CoordinatorPidReadinessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process ancestry test")
    def test_real_child_pid_is_accepted(self):
        with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"]) as child:
            try:
                self.assertTrue(supervisor._is_child_process(child.pid, os.getpid()))
            finally:
                child.terminate()

    @unittest.skipUnless(os.name == "nt", "Windows process ancestry test")
    def test_unrelated_pid_is_rejected(self):
        with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"]) as child:
            try:
                self.assertFalse(supervisor._is_child_process(os.getpid(), child.pid))
            finally:
                child.terminate()

    @unittest.skipUnless(os.name == "nt", "Windows process ancestry test")
    def test_grandchild_pid_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = pathlib.Path(tmp) / "grandchild.pid"
            script = (
                "import pathlib, subprocess, sys, time\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(p.pid))\n"
                "p.wait()\n"
            )
            parent = subprocess.Popen([sys.executable, "-c", script, str(marker)])
            try:
                import time
                for _ in range(100):
                    if marker.exists():
                        break
                    if parent.poll() is not None:
                        self.fail("intermediate Python process exited early")
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), "grandchild PID not recorded")
                self.assertTrue(supervisor._is_child_process(int(marker.read_text()), os.getpid()))
            finally:
                parent.terminate()
                parent.wait(timeout=10)

    def test_health_pid_requires_process_ownership(self):
        import io
        proc = mock.Mock()
        proc.pid = 101
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return b'{"ok":true,"pid":202}'
        with mock.patch.object(supervisor.urllib.request, "urlopen", return_value=Response()):
            with mock.patch.object(supervisor, "_is_child_process", return_value=False):
                self.assertFalse(supervisor._ready("coordinator", proc, None))
            with mock.patch.object(supervisor, "_is_child_process", return_value=True):
                self.assertTrue(supervisor._ready("coordinator", proc, None))

    def test_health_pid_rejects_boolean(self):
        proc = mock.Mock()
        proc.pid = 1
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return b'{"ok":true,"pid":true}'
        with mock.patch.object(supervisor.urllib.request, "urlopen", return_value=Response()):
            self.assertFalse(supervisor._ready("coordinator", proc, None))


class ReleaseSupervisorTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows job object test")
    def test_job_close_terminates_running_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp)
            try:
                with supervisor._child_job(proc):
                    self.assertIsNone(proc.poll())
                self.assertIsNotNone(proc.wait(timeout=10))
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    @unittest.skipUnless(os.name == "nt", "Windows job object test")
    def test_job_context_exception_terminates_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp)
            try:
                with self.assertRaisesRegex(RuntimeError, "test interruption"):
                    with supervisor._child_job(proc):
                        self.assertIsNone(proc.poll())
                        raise RuntimeError("test interruption")
                self.assertIsNotNone(proc.wait(timeout=10))
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    @unittest.skipUnless(os.name == "nt", "Windows named mutex test")
    def test_supervisor_mutex_can_be_reacquired_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            with supervisor._single_instance(tmp, "worker"):
                pass
            with supervisor._single_instance(tmp, "worker"):
                pass

    @unittest.skipUnless(os.name == "nt", "Windows supervisor crash test")
    def test_killed_supervisor_releases_mutex_and_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            marker = root / "child-pid.txt"
            assigned = root / "job-assigned.txt"
            child = root / "child.py"
            child.write_text(
                "import os, pathlib, time\n"
                "pathlib.Path(os.environ['GRID_TEST_CHILD_PID']).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            launcher = root / "supervisor.py"
            launcher.write_text(
                "import os, subprocess, sys, time\n"
                "from grid.release_supervisor import _single_instance, _child_job\n"
                "with _single_instance(sys.argv[1], 'worker'):\n"
                "    p = subprocess.Popen([sys.executable, sys.argv[2]], env=os.environ.copy())\n"
                "    with _child_job(p):\n"
                "        from pathlib import Path\n"
                "        Path(sys.argv[3]).write_text('assigned')\n"
                "        p.wait()\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["GRID_TEST_CHILD_PID"] = str(marker)
            env["PYTHONPATH"] = str(pathlib.Path(supervisor.__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
            parent = subprocess.Popen([sys.executable, str(launcher), str(root), str(child), str(assigned)], env=env)
            try:
                for _ in range(100):
                    if marker.exists() and assigned.exists():
                        break
                    if parent.poll() is not None:
                        self.fail("supervisor exited before child started")
                    import time
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), "child did not start")
                self.assertTrue(assigned.exists(), "child was not assigned to Windows Job Object")
                child_pid = int(marker.read_text())
                parent.kill()
                parent.wait(timeout=10)
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
                kernel.WaitForSingleObject.restype = wintypes.DWORD
                kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
                kernel.CloseHandle.restype = wintypes.BOOL
                handle = kernel.OpenProcess(0x00100000, False, child_pid)
                if handle:
                    try:
                        self.assertEqual(kernel.WaitForSingleObject(handle, 10000), 0)
                    finally:
                        kernel.CloseHandle(handle)
                with supervisor._single_instance(root, "worker"):
                    pass
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait()

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

    def test_crash_processing_waits_for_inflight_confirmation(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            proc = mock.Mock()
            proc.poll.return_value = None
            entered = threading.Event()
            release = threading.Event()
            completed = threading.Event()
            def slow_ready(*args):
                entered.set()
                if not release.wait(timeout=5):
                    raise RuntimeError("readiness wait timed out")
                return True
            def crash():
                supervisor._after_exit(root, version, 1, exit_code=1)
                completed.set()
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                with mock.patch.object(supervisor, "_ready", side_effect=slow_ready):
                    confirm_thread = threading.Thread(
                        target=supervisor._confirm,
                        args=(root, version, proc, 1, "coordinator", None),
                    )
                    confirm_thread.start()
                    try:
                        self.assertTrue(entered.wait(timeout=5))
                        crash_thread = threading.Thread(target=crash)
                        crash_thread.start()
                        self.assertFalse(completed.wait(timeout=0.1),
                                         "crash processing bypassed confirmation lock")
                    finally:
                        release.set()
                        confirm_thread.join(timeout=5)
                        if "crash_thread" in locals():
                            crash_thread.join(timeout=5)
            self.assertTrue(completed.is_set())
            self.assertFalse((root / "pending.version").exists())
            self.assertFalse((root / "pending-crashes.txt").exists())

    def test_child_exiting_during_readiness_does_not_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("2")
            proc = mock.Mock()
            proc.poll.side_effect = [None, 1]
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                with mock.patch.object(supervisor, "_ready", return_value=True):
                    supervisor._confirm(root, version, proc, 1, mode="coordinator")
            self.assertTrue((root / "pending.version").exists())
            self.assertEqual((root / "pending-crashes.txt").read_text(), "2")

    def test_missing_current_marker_blocks_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "pending.version").write_text(version)
            proc = mock.Mock()
            proc.poll.return_value = None
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                supervisor._confirm(root, version, proc, 1)
            self.assertTrue((root / "pending.version").exists())

    def test_stale_supervisor_does_not_confirm_pending_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            (root / "current.version").write_text(old)
            (root / "pending.version").write_text(new)
            proc = mock.Mock()
            proc.poll.return_value = None
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                supervisor._confirm(root, new, proc, 1)
            self.assertEqual((root / "pending.version").read_text(), new)

    def test_unresolved_journal_does_not_confirm_pending_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            new = "b" * 40
            (root / "current.version").write_text(new)
            (root / "pending.version").write_text(new)
            (root / "switch-journal.json").write_text('{"phase":"prepared"}')
            proc = mock.Mock()
            proc.poll.return_value = None
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                supervisor._confirm(root, new, proc, 1)
            self.assertTrue((root / "pending.version").exists())

    def test_successful_confirmation_clears_previous_crash_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("2")
            proc = mock.Mock()
            proc.poll.return_value = None
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                supervisor._confirm(root, version, proc, 1)
            self.assertFalse((root / "pending.version").exists())
            self.assertFalse((root / "pending-crashes.txt").exists())

    def test_failed_confirmation_preserves_previous_crash_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("2")
            proc = mock.Mock()
            proc.poll.return_value = 1
            with mock.patch.object(supervisor.time, "sleep", return_value=None):
                supervisor._confirm(root, version, proc, 1)
            self.assertTrue((root / "pending.version").exists())
            self.assertEqual((root / "pending-crashes.txt").read_text(), "2")

    def test_negative_crash_counter_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("-100")
            self.assertFalse(supervisor._after_exit(root, version, 1, exit_code=1))
            self.assertEqual((root / "pending-crashes.txt").read_text(), "1")

    def test_implausibly_large_crash_counter_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("999999999999999999999999")
            self.assertFalse(supervisor._after_exit(root, version, 1, exit_code=1))
            self.assertEqual((root / "pending-crashes.txt").read_text(), "1")

    def test_extremely_long_crash_counter_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("9" * 10000)
            self.assertFalse(supervisor._after_exit(root, version, 1, exit_code=1))
            self.assertEqual((root / "pending-crashes.txt").read_text(), "1")

    def test_non_numeric_crash_counter_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            version = "b" * 40
            (root / "current.version").write_text(version)
            (root / "pending.version").write_text(version)
            (root / "pending-crashes.txt").write_text("corrupted")
            self.assertFalse(supervisor._after_exit(root, version, 1, exit_code=1))
            self.assertEqual((root / "pending-crashes.txt").read_text(), "1")

    def test_clean_shutdown_does_not_increment_crash_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            (root / "previous.version").write_text(old)
            (root / "current.version").write_text(new)
            (root / "pending.version").write_text(new)
            previous = root / "releases" / old
            previous.mkdir(parents=True)
            (previous / "run_worker.py").write_text("# fixture")
            for _ in range(5):
                self.assertFalse(supervisor._after_exit(root, new, 30, exit_code=0))
            self.assertFalse((root / "pending-crashes.txt").exists())
            self.assertEqual((root / "current.version").read_text(), new)
            self.assertTrue((root / "pending.version").exists())
            self.assertFalse(supervisor._after_exit(root, new, 1, exit_code=1))
            self.assertEqual((root / "pending-crashes.txt").read_text(), "1")

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

    def test_symlinked_previous_release_cannot_escape_release_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            external = root / "external"
            external.mkdir()
            (external / "run_worker.py").write_text("# not an installed release")
            releases = root / "releases"
            releases.mkdir()
            try:
                (releases / old).symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable")
            (root / "previous.version").write_text(old)
            (root / "current.version").write_text(new)
            (root / "pending.version").write_text(new)
            for _ in range(3):
                self.assertFalse(supervisor._after_exit(root, new, 1, exit_code=1, mode="worker"))
            self.assertEqual((root / "current.version").read_text(), new)
            self.assertTrue((root / "pending.version").exists())

    def test_invalid_previous_release_marker_blocks_rollback(self):
        for invalid in ("../outside", "..\\outside", "", "bootstrap", "A" * 40, "a" * 39, "g" * 40):
            with self.subTest(previous=invalid), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                version = "b" * 40
                (root / "previous.version").write_text(invalid)
                (root / "current.version").write_text(version)
                (root / "pending.version").write_text(version)
                for _ in range(3):
                    self.assertFalse(supervisor._after_exit(root, version, 1, exit_code=1, mode="worker"))
                self.assertEqual((root / "current.version").read_text(), version)
                self.assertFalse((root / "failed.version").exists())

    def test_worker_cannot_roll_back_to_coordinator_only_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            for name, value in (("previous.version", old), ("current.version", new), ("pending.version", new)):
                (root / name).write_text(value)
            previous = root / "releases" / old / "grid"
            previous.mkdir(parents=True)
            (previous / "coordinator.py").write_text("# coordinator only")
            for _ in range(3):
                self.assertFalse(supervisor._after_exit(root, new, 1, exit_code=1, mode="worker"))
            self.assertEqual((root / "current.version").read_text(), new)
            self.assertTrue((root / "pending.version").exists())

    def test_coordinator_cannot_roll_back_to_worker_only_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            old, new = "a" * 40, "b" * 40
            for name, value in (("previous.version", old), ("current.version", new), ("pending.version", new)):
                (root / name).write_text(value)
            previous = root / "releases" / old
            previous.mkdir(parents=True)
            (previous / "run_worker.py").write_text("# worker only")
            for _ in range(3):
                self.assertFalse(supervisor._after_exit(root, new, 1, exit_code=1, mode="coordinator"))
            self.assertEqual((root / "current.version").read_text(), new)
            self.assertTrue((root / "pending.version").exists())

    def test_no_rollback_to_missing_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            new = "b" * 40
            (root / "pending.version").write_text(new)
            (root / "current.version").write_text(new)
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
