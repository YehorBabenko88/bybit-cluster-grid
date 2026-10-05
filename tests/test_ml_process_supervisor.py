import asyncio
import sys

import psutil
import pytest

from grid.ml_process_supervisor import ProcessLimitError,run_supervised_process


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
