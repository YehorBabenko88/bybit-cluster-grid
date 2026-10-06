import asyncio
import pytest
from grid.ml_remote_lease import run_remote_lease


class Lost:
    async def renew(self,job):return None


def test_remote_lease_loss_cancels_work():
    async def scenario():
        cancelled=asyncio.Event()
        async def work():
            try:await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set();raise
        with pytest.raises(RuntimeError,match="lease lost"):
            await run_remote_lease(Lost(),{"id":"j","lease_generation":2},work,renew_every=.01)
        assert cancelled.is_set()
    asyncio.run(scenario())


def test_transport_client_has_no_database_dependency():
    from pathlib import Path
    s=Path("grid/ml_transport_client.py").read_text(encoding="utf-8")
    assert "postgres" not in s.lower()
    assert "node_credential()" in s
    assert "X-Node-Credential" in s


class RenewError:
    async def renew(self,job):
        raise ConnectionError("CONTROL unreachable")


def test_remote_renew_exception_cancels_work():
    async def scenario():
        cancelled=asyncio.Event()
        async def work():
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
        with pytest.raises(ConnectionError,match="CONTROL unreachable"):
            await run_remote_lease(
                RenewError(),{"id":"j","lease_generation":2},work,renew_every=.01
            )
        assert cancelled.is_set()
    asyncio.run(scenario())


def test_remote_lease_caller_cancellation_cleans_work():
    async def scenario():
        cancelled=asyncio.Event()
        async def work():
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()
        outer=asyncio.create_task(
            run_remote_lease(Lost(),{"id":"j","lease_generation":2},work,renew_every=30)
        )
        await asyncio.sleep(.01)
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer
        assert cancelled.is_set()
    asyncio.run(scenario())
