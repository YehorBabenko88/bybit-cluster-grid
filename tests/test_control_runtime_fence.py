import asyncio
import time,os
from pathlib import Path
from contextlib import asynccontextmanager

import pytest

from grid.control_runtime import Epoch,FencedPool,LeaderFenceError,epoch_context,ControlRuntime,leader_pool_effect


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


def test_revoked_epoch_cannot_start_filesystem_effects():
    async def run():
        calls=[]
        @leader_pool_effect
        async def cleanup(pool):calls.append('delete')
        pool=FencedPool(None)
        token=Epoch('control',1);token.active=False
        with epoch_context(token):
            with pytest.raises(LeaderFenceError):await cleanup(pool)
        assert calls==[]
    asyncio.run(run())


def test_blocked_event_loop_cannot_admit_next_file_delete_after_expiry(tmp_path,monkeypatch):
    from grid.maintenance import cleanup_owned_temp_files
    async def run():
        paths=[tmp_path/'a.tmp',tmp_path/'b.tmp']
        for p in paths:p.write_text('test');os.utime(p,(0,0))
        original=Path.unlink
        def slow_unlink(p,*args,**kwargs):
            result=original(p,*args,**kwargs)
            time.sleep(.04)
            return result
        monkeypatch.setattr(Path,'unlink',slow_unlink)
        class Connection:
            @asynccontextmanager
            async def transaction(self):yield
            async def fetchrow(self,*args):return {}
            async def fetchval(self,*args):return .02
        class Pool:
            @asynccontextmanager
            async def acquire(self):yield Connection()
        with epoch_context(Epoch('control',1)):
            with pytest.raises((LeaderFenceError,TimeoutError)):
                async with FencedPool(Pool()).effect_guard():cleanup_owned_temp_files(tmp_path)
        assert sum(p.exists() for p in paths)==1
    asyncio.run(run())
