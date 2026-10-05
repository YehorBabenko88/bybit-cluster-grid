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
