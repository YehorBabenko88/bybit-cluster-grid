"""Two actual election runtimes plus transactional persistence fencing."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest

from grid.control_runtime import ControlRuntime,FencedPool,Epoch,LeaderFenceError,epoch_context
from grid.floating_leader import FloatingLeader
from test_collection_ownership_postgres import database

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='isolated PostgreSQL required')

async def schema(pool):
    await pool.execute("""CREATE TABLE service_leases(service_key text PRIMARY KEY,
      owner text NOT NULL,lease_until timestamptz NOT NULL,heartbeat_at timestamptz,
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb)""")


def test_two_control_runtimes_start_only_one_singleton_then_take_over():
    async def run():
        async with database() as pool:
            await schema(pool)
            fenced=FencedPool(pool);starts=[];stops=[]
            def callbacks(name):
                async def start(epoch):
                    await fenced.execute('INSERT INTO canonical_writes VALUES($1,$2)',name,epoch%1000000)
                    starts.append(name)
                async def stop():stops.append(name)
                return start,stop
            a=ControlRuntime(pool,*callbacks('a'),node_id='a',lease_seconds=3,renew_seconds=.1)
            b=ControlRuntime(pool,*callbacks('b'),node_id='b',lease_seconds=3,renew_seconds=.1)
            a.start();b.start()
            try:
                for _ in range(250):
                    if starts:break
                    await asyncio.sleep(.02)
                assert len(starts)==1 and sum([a.ready,b.ready])==1
                winner,loser=(a,b) if a.ready else (b,a)
                old=winner.token
                await winner.stop()
                assert not old.active
                # A campaign COMMIT can succeed on PostgreSQL while its client
                # times out. The unknown epoch must expire before takeover.
                # Cover the complete three-second lease, not just two seconds.
                for _ in range(250):
                    if loser.ready:break
                    await asyncio.sleep(.02)
                assert loser.ready and len(starts)==2
                with epoch_context(old):
                    with pytest.raises(LeaderFenceError):await fenced.execute('INSERT INTO canonical_writes VALUES($1,$2)','stale',1)
                assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==2
            finally:
                await a.stop();await b.stop()
    asyncio.run(run())


def test_control_deadline_cancels_deferred_commit():
    async def run():
        async with database() as pool:
            await schema(pool)
            leader=FloatingLeader(pool,'old',lease_seconds=3,renew_seconds=.1)
            assert await leader.campaign()
            await pool.execute("""CREATE FUNCTION slow_commit() RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN PERFORM pg_sleep(.5);RETURN NEW;END $$""")
            await pool.execute("""CREATE CONSTRAINT TRIGGER slow_commit_trigger AFTER INSERT ON canonical_writes
              DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION slow_commit()""")
            await pool.execute("UPDATE service_leases SET lease_until=clock_timestamp()+interval '250 milliseconds'")
            with epoch_context(Epoch('old',leader.epoch)):
                with pytest.raises(TimeoutError):
                    await FencedPool(pool).execute("INSERT INTO canonical_writes VALUES('old',1)")
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
    asyncio.run(run())


def test_long_control_transaction_rolls_back_before_takeover():
    async def run():
        async with database() as pool:
            await schema(pool)
            leader=FloatingLeader(pool,'old',lease_seconds=3,renew_seconds=.1)
            assert await leader.campaign()
            old=Epoch('old',leader.epoch)
            fenced=FencedPool(pool)
            await pool.execute("UPDATE service_leases SET lease_until=clock_timestamp()+interval '250 milliseconds'")
            entered=asyncio.Event()
            async def old_write():
                with epoch_context(old):
                    async with fenced.acquire() as c:
                        await c.execute("INSERT INTO canonical_writes VALUES('old',1)")
                        entered.set()
                        await asyncio.sleep(.5)
            task=asyncio.create_task(old_write())
            await entered.wait()
            successor=FloatingLeader(pool,'new',lease_seconds=3,renew_seconds=.1)
            election=asyncio.create_task(successor.campaign())
            await asyncio.sleep(.1)
            assert not election.done()
            with pytest.raises(TimeoutError):await task
            won=await election
            if not won:assert await successor.campaign()
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            with epoch_context(old):
                with pytest.raises(LeaderFenceError):await fenced.execute("INSERT INTO canonical_writes VALUES('stale',1)")
    asyncio.run(run())


def test_control_db_outage_revokes_old_task_epoch_and_recovers():
    async def run():
        async with database() as pool:
            await schema(pool)
            class ConnectionFault:
                down=False
                @asynccontextmanager
                async def acquire(self):
                    if self.down:raise ConnectionError('synthetic PostgreSQL transport outage')
                    async with pool.acquire() as c:yield c
                async def execute(self,*args):
                    async with self.acquire() as c:return await c.execute(*args)
            transport=ConnectionFault();fenced=FencedPool(transport);events=[]
            async def start(epoch):
                await fenced.execute("INSERT INTO canonical_writes VALUES('leader',$1)",epoch%1000000)
                events.append('start')
            async def stop():events.append('stop')
            runtime=ControlRuntime(transport,start,stop,node_id='control',lease_seconds=3,renew_seconds=.1)
            runtime.start()
            try:
                for _ in range(100):
                    if runtime.ready:break
                    await asyncio.sleep(.02)
                assert runtime.ready
                old=runtime.token
                transport.down=True
                for _ in range(100):
                    if not runtime.ready:break
                    await asyncio.sleep(.02)
                assert not runtime.ready and not old.active
                transport.down=False
                await pool.execute("UPDATE service_leases SET lease_until=clock_timestamp()-interval '1 second'")
                for _ in range(100):
                    if runtime.ready:break
                    await asyncio.sleep(.02)
                assert runtime.ready and runtime.token.generation>old.generation
                assert events[:3]==['start','stop','start']
                with epoch_context(old):
                    with pytest.raises(LeaderFenceError):await fenced.execute("INSERT INTO canonical_writes VALUES('stale',1)")
            finally:await runtime.stop()
    asyncio.run(run())
