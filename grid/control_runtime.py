"""Bind CONTROL singleton lifetimes and every persistence transaction to an epoch."""
import asyncio
from contextlib import asynccontextmanager,contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import socket
import uuid
from functools import wraps
from starlette.responses import JSONResponse

from .floating_leader import FloatingLeader

class LeaderFenceError(RuntimeError):pass

@dataclass
class Epoch:
    owner:str
    generation:int
    active:bool=True

_epoch=ContextVar('control_epoch',default=None)
_scope=ContextVar('control_transaction',default=None)

@contextmanager
def epoch_context(token):
    marker=_epoch.set(token)
    try:yield
    finally:_epoch.reset(marker)


def leader_effect(function):
    """Guard legacy non-DB command effects with the same lease transaction."""
    @wraps(function)
    async def guarded(db,*args,**kwargs):
        if isinstance(db.pool,FencedPool):
            async with db.pool.effect_guard():return await function(db,*args,**kwargs)
        return await function(db,*args,**kwargs)
    return guarded


class EpochMiddleware:
    """Pure ASGI: route cancellation and transaction run on the same task.

    Control POST responses are released only after the enclosing fence commits.
    Ingest uses its own atomic persistence fence and post-commit cache publication.
    """
    def __init__(self,app,runtime,pool):self.app=app;self.runtime=runtime;self.pool=pool
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('path')=='/health':
            return await self.app(scope,receive,send)
        runtime=self.runtime()
        if runtime is None or not runtime.ready or runtime.token is None or not runtime.token.active:
            return await JSONResponse({'detail':'CONTROL is not the active leader'},status_code=503)(scope,receive,send)
        try:
            with epoch_context(runtime.token):
                if scope.get('method')!='POST' or scope.get('path','').startswith('/ingest/'):
                    return await self.app(scope,receive,send)
                messages=[];size=0
                async def buffered(message):
                    nonlocal size
                    size+=len(message.get('body',b''))
                    if size>2*1024**2:raise LeaderFenceError('CONTROL response exceeds bound')
                    messages.append(message)
                async with self.pool().effect_guard():
                    await self.app(scope,receive,buffered)
                for message in messages:await send(message)
        except (LeaderFenceError,TimeoutError):
            await JSONResponse({'detail':'CONTROL epoch lost or operation timed out'},status_code=503)(scope,receive,send)


class FencedPool:
    """All existing pool consumers receive a checked, rollback-capable boundary."""
    def __init__(self,raw,max_seconds=10):self.raw=raw;self.max_seconds=max_seconds

    def actor(self):
        actor=_epoch.get()
        if actor is None or not actor.active:
            raise LeaderFenceError('CONTROL epoch is absent or revoked')
        return actor

    async def remaining(self,c,actor):
        value=await c.fetchval("""SELECT extract(epoch from lease_until-clock_timestamp())
          FROM service_leases WHERE service_key='control-plane-leader' AND owner=$1
          AND (metadata->>'epoch')::bigint=$2""",actor.owner,actor.generation)
        if not actor.active or value is None or value<=0:
            raise LeaderFenceError('CONTROL lease or epoch is stale')
        return float(value)

    @asynccontextmanager
    async def _acquire(self,effect=False):
        actor=self.actor();task=asyncio.current_task();current=_scope.get()
        if current and current['active'] and current['pool'] is self and current['actor'] is actor and current['owner'] in (None,task):
            current['owner']=task
            await self.remaining(current['connection'],actor)
            yield current['connection']
            return
        # Bound waiting for pool/row locks as well as the body. A stale task
        # cannot keep a transaction/side-effect permission alive indefinitely.
        async with asyncio.timeout(self.max_seconds):
            async with asyncio.timeout(None) as lease_timeout:
                async with self.raw.acquire() as c:
                    async with c.transaction():
                        await c.fetchrow("SELECT service_key FROM service_leases WHERE service_key='control-plane-leader' FOR SHARE")
                        ttl=await self.remaining(c,actor)
                        lease_timeout.reschedule(asyncio.get_running_loop().time()+ttl)
                        state={'pool':self,'connection':c,'owner':None if effect else task,'active':True,'actor':actor}
                        marker=_scope.set(state)
                        try:
                            yield c
                            await self.remaining(c,actor)
                        finally:
                            state['active']=False
                            _scope.reset(marker)
                    # The lease timer remains active through transaction COMMIT,
                    # including deferred constraints and server-side waits.

    def acquire(self):return self._acquire()
    def effect_guard(self):return self._acquire(effect=True)
    async def _call(self,name,*args,**kwargs):
        async with self.acquire() as c:return await getattr(c,name)(*args,**kwargs)
    async def execute(self,*args,**kwargs):return await self._call('execute',*args,**kwargs)
    async def executemany(self,*args,**kwargs):return await self._call('executemany',*args,**kwargs)
    async def fetch(self,*args,**kwargs):return await self._call('fetch',*args,**kwargs)
    async def fetchrow(self,*args,**kwargs):return await self._call('fetchrow',*args,**kwargs)
    async def fetchval(self,*args,**kwargs):return await self._call('fetchval',*args,**kwargs)


class RuntimeElection(FloatingLeader):
    async def campaign(self):
        async with asyncio.timeout(self.renew_seconds):return await super().campaign()
    async def renew(self):
        if not self.is_leader:return False
        async with asyncio.timeout(self.renew_seconds):
            async with self.pool.acquire() as c:
                async with c.transaction():
                    await c.fetchrow("SELECT service_key FROM service_leases WHERE service_key='control-plane-leader' FOR UPDATE")
                    result=await c.execute("""UPDATE service_leases
                      SET lease_until=clock_timestamp()+($3*interval '1 second'),heartbeat_at=clock_timestamp()
                      WHERE service_key='control-plane-leader' AND owner=$1
                      AND (metadata->>'epoch')::bigint=$2 AND lease_until>clock_timestamp()""",
                      self.node_id,self.epoch,self.lease_seconds)
        self.is_leader=result.endswith(' 1')
        if not self.is_leader:self.epoch=None
        return self.is_leader


class ControlRuntime:
    def __init__(self,pool,start_services,stop_services,node_id=None,lease_seconds=20,renew_seconds=5):
        self.election=RuntimeElection(pool,node_id or socket.gethostname()+':'+uuid.uuid4().hex,
                                      lease_seconds,renew_seconds)
        self.start_services=start_services;self.stop_services=stop_services
        self.token=None;self.ready=False;self.cleanup_pending=False;self.task=None

    async def _gain(self,epoch):
        if self.cleanup_pending or self.token is not None:await self._loss()
        self.token=Epoch(self.election.node_id,epoch)
        try:
            with epoch_context(self.token):
                async with asyncio.timeout(self.election.lease_seconds/2):
                    await self.start_services(epoch)
        except BaseException:
            await self._loss()
            raise
        self.ready=True

    async def _loss(self):
        self.ready=False
        if self.token:self.token.active=False
        self.cleanup_pending=True
        async with asyncio.timeout(self.election.renew_seconds):
            await self.stop_services()
        self.cleanup_pending=False
        self.token=None

    def start(self):
        self.task=asyncio.create_task(self.election.run(self._gain,self._loss))

    async def stop(self):
        self.ready=False
        if self.token:self.token.active=False
        self.election.stop()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
        # Failed cleanup never releases the lease early.
        await self.election.shutdown(on_loss=self._loss)
        if self.cleanup_pending or self.token is not None:await self._loss()
