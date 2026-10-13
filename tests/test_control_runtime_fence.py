import asyncio
from contextlib import asynccontextmanager

import pytest

from grid.control_runtime import Epoch,FencedPool,LeaderFenceError,epoch_context,ControlRuntime


def test_persistence_rejects_missing_or_revoked_epoch():
    async def run():
        class Pool:
            def acquire(self):raise AssertionError('revoked epoch must not touch DB')
        pool=FencedPool(Pool())
        with pytest.raises(LeaderFenceError):await pool.execute('mutation')
        token=Epoch('control',3);token.active=False
        with epoch_context(token):
            with pytest.raises(LeaderFenceError):await pool.execute('mutation')
    asyncio.run(run())


def test_shutdown_cleans_services_even_if_election_already_cleared_lease():
    async def run():
        events=[]
        async def start(epoch):events.append('start')
        async def stop():events.append('stop')
        runtime=ControlRuntime(None,start,stop)
        await runtime._gain(1)
        runtime.election.is_leader=False;runtime.election.epoch=None
        await runtime.stop()
        assert events==['start','stop']
    asyncio.run(run())


def test_lease_timeout_covers_delayed_commit_not_only_transaction_body():
    async def run():
        class Connection:
            committed=False
            @asynccontextmanager
            async def transaction(self):
                yield
                await asyncio.sleep(.05)
                self.committed=True
            async def fetchrow(self,*args):return {'service_key':'control-plane-leader'}
            async def fetchval(self,*args):return .02
            async def execute(self,*args):return 'UPDATE 1'
        connection=Connection()
        class Pool:
            @asynccontextmanager
            async def acquire(self):yield connection
        with epoch_context(Epoch('control',1)):
            with pytest.raises(TimeoutError):await FencedPool(Pool()).execute('mutation')
        assert not connection.committed
    asyncio.run(run())


def test_failed_cleanup_blocks_singleton_restart():
    async def run():
        events=[]
        async def start(epoch):events.append(('start',epoch))
        async def stop():
            events.append(('stop',None))
            raise RuntimeError('cleanup failed')
        runtime=ControlRuntime(None,start,stop)
        await runtime._gain(1)
        with pytest.raises(RuntimeError):await runtime._loss()
        with pytest.raises(RuntimeError):await runtime._gain(2)
        assert events==[('start',1),('stop',None),('stop',None)]
        assert not runtime.ready
    asyncio.run(run())
