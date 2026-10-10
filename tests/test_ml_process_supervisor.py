import asyncio
import sys

import psutil
import pytest

from grid.ml_process_supervisor import ProcessLimitError,run_supervised_process
from grid.ml_worker_protocol import run_with_lease


def test_supervised_process_returns_stdout():
    async def run():
        out=await run_supervised_process(
            [sys.executable,"-c","print('ok')"],
            timeout_seconds=5,
        )
        assert out.decode().strip()=="ok"
    asyncio.run(run())


def test_supervised_process_timeout_kills_child():
    async def run():
        marker=[]
        code="import time; time.sleep(30)"
        with pytest.raises(ProcessLimitError,match="timeout"):
            await run_supervised_process(
                [sys.executable,"-c",code],
                timeout_seconds=.1,
                poll_seconds=.02,
                grace_seconds=.05,
            )
    asyncio.run(run())


def test_supervised_process_ram_limit_kills_worker():
    async def run():
        code="import time; x=bytearray(32*1024*1024); time.sleep(30)"
        with pytest.raises(ProcessLimitError,match="RAM limit"):
            await run_supervised_process(
                [sys.executable,"-c",code],
                timeout_seconds=5,
                ram_limit_mb=12,
                poll_seconds=.02,
                grace_seconds=.05,
            )
    asyncio.run(run())


def test_lease_loss_propagates_cancel_into_subprocess_supervisor():
    async def run():
        class LeasePool:
            async def execute(self,sql,*args):
                if "UPDATE ml_jobs SET lease_until" in sql:
                    return "UPDATE 0"
                return "UPDATE 1"
        async def work():
            return await run_supervised_process(
                [sys.executable,"-c","import time; time.sleep(30)"],
                timeout_seconds=60,
                poll_seconds=.02,
                grace_seconds=.05,
            )
        with pytest.raises(RuntimeError,match="lease lost"):
            await run_with_lease(
                LeasePool(),{"id":"job-1","lease_generation":2},"node-1",
                work,lease_seconds=1,renew_every=.05,
            )
    asyncio.run(run())


def test_verbose_subprocess_does_not_deadlock_pipe():
    async def run():
        code="import sys; sys.stdout.write('x'*2000000); sys.stderr.write('y'*2000000)"
        out=await run_supervised_process([sys.executable,"-c",code],timeout_seconds=10,poll_seconds=.02)
        assert len(out)<=8192
        assert out.endswith(b"x"*100)
    asyncio.run(run())


def test_supervisor_rejects_nonpositive_timeout():
    async def run():
        with pytest.raises(ValueError):
            await run_supervised_process([sys.executable,"-c","pass"],timeout_seconds=0)
    asyncio.run(run())


def test_supervisor_keeps_exact_last_bytes_across_chunk_boundaries():
    async def run():
        code = "import sys; sys.stdout.buffer.write(b'a'*5000+b'b'*5000); sys.stdout.flush()"
        out = await run_supervised_process(
            [sys.executable, "-c", code], timeout_seconds=5, poll_seconds=.02
        )
        assert out == b"a"*3192 + b"b"*5000
    asyncio.run(run())


def test_supervisor_rejects_nonpositive_ram_limit():
    async def run():
        with pytest.raises(ValueError, match="ram_limit_mb must be positive"):
            await run_supervised_process(
                [sys.executable, "-c", "pass"],
                timeout_seconds=5, ram_limit_mb=0,
            )
    asyncio.run(run())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object integration")
def test_windows_suspended_job_runs_only_after_assignment():
    async def run():
        out = await run_supervised_process(
            [sys.executable, "-c", "print(\'suspended-job-ok\')"],
            timeout_seconds=10, poll_seconds=.05,
        )
        assert out.decode().strip() == "suspended-job-ok"
    asyncio.run(run())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object integration")
def test_windows_job_close_kills_descendant(tmp_path):
    import subprocess
    import time
    from grid.ml_windows_job import WindowsJob

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=0x00000004,  # CREATE_SUSPENDED (Win32),
    )
    job = None
    try:
        job = WindowsJob(child.pid, resume_primary_thread=True)
        assert child.poll() is None
        job.close()
        job = None
        child.wait(timeout=10)
        assert child.returncode is not None
    finally:
        if job is not None:
            job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object integration")
def test_windows_parent_crash_kills_ml_process_tree(tmp_path):
    import os
    import subprocess
    import time

    child_pid_file = tmp_path / "child.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    child_code = (
        "import os,subprocess,sys,time,pathlib;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid));"
        "time.sleep(120)"
    )
    parent_code = (
        "import asyncio,sys;"
        "from grid.ml_process_supervisor import run_supervised_process;"
        "asyncio.run(run_supervised_process("
        "[sys.executable,'-c',sys.argv[2],sys.argv[1]],"
        "timeout_seconds=120,poll_seconds=.05))"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code, str(grandchild_pid_file), child_code],
        cwd=os.getcwd(),
    )
    try:
        deadline=time.monotonic()+15
        while not grandchild_pid_file.exists() and time.monotonic()<deadline:
            if parent.poll() is not None:
                pytest.fail(f"supervisor parent exited prematurely: {parent.returncode}")
            time.sleep(.1)
        assert grandchild_pid_file.exists(), "ML descendant did not start"
        descendant_pid=int(grandchild_pid_file.read_text())
        descendant=psutil.Process(descendant_pid)
        ml_child_pid=descendant.ppid()
        assert psutil.pid_exists(ml_child_pid)
        parent.kill()
        parent.wait(timeout=10)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and (psutil.pid_exists(ml_child_pid) or psutil.pid_exists(descendant_pid)):
            time.sleep(.1)
        assert not psutil.pid_exists(ml_child_pid)
        assert not psutil.pid_exists(descendant_pid)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if grandchild_pid_file.exists():
            try:
                pid=int(grandchild_pid_file.read_text())
                if psutil.pid_exists(pid):psutil.Process(pid).kill()
            except (ValueError,psutil.Error):
                pass
