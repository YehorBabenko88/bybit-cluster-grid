import asyncio
import hashlib
import aiohttp
import os

from .config import settings
from .resources import NODE_ID
from .segment_wal import SegmentWAL
from .write_queue import BoundedWriteQueue


class MicroEventStorage:
    """Durable remote sink for high-frequency research events.

    Workers remain DB-less. Events are first appended to a dedicated WAL and
    acknowledged only after CONTROL accepts them.
    """
    def __init__(self):
        root=os.path.join(
            os.getenv("ProgramData",os.getcwd()),
            "BybitClusterGrid",
            "micro-spool",
        )
        self.spool=SegmentWAL(
            root,
            max_bytes=int(settings.micro_event_spool_max_gb*1024**3),
        )
        self.http=None
        self.replay_task=None
        self.replay_done=asyncio.Event(); self.replay_done.set()
        self.write_queue=BoundedWriteQueue(
            self._save_spooled,
            maxsize=20000,
            workers=1,
        )

    async def start(self):
        self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        await self.write_queue.start()
        pending=self.spool.iter_recover()
        self.replay_done.clear()
        self.replay_task=asyncio.create_task(self._replay(pending))

    async def _replay(self,pending):
        try:
            # Deterministic node jitter prevents all agents from hammering CONTROL
            # in the same second after a fleet/network outage.
            jitter=max(0.0,float(settings.replay_start_jitter_seconds))
            if jitter:
                seed=int(hashlib.sha256(NODE_ID.encode("utf-8")).hexdigest()[:8],16)
                await asyncio.sleep((seed%10000)/10000.0*jitter)
            rate=max(0.1,float(settings.replay_micro_per_second))
            interval=1.0/rate
            for record_id,row in pending:
                await self.write_queue.put(record_id,row)
                await asyncio.sleep(interval)
        finally:
            self.replay_done.set()

    async def insert_event(self,symbol,event_ts,event_type,payload):
        await self.replay_done.wait()
        if self.spool.ratio()>=settings.spool_critical_ratio:
            raise BufferError("Grid micro-event WAL critical threshold reached; load shedding required")
        row={
            "symbol":symbol,
            "event_ts":int(event_ts),
            "event_type":event_type,
            "payload":payload,
        }
        record_id=await self.spool.append(row)
        await self.write_queue.put(record_id,row)

    async def close(self,drain_timeout=5):
        if self.replay_task is not None and not self.replay_task.done():
            self.replay_task.cancel()
            await asyncio.gather(self.replay_task,return_exceptions=True)
        self.replay_task=None
        await self.write_queue.close(drain_timeout)
        if self.http is not None:
            await self.http.close(); self.http=None

    async def _save_spooled(self,record_id,row):
        from .credential_store import node_credential

        headers={
            "X-Grid-Token":settings.grid_shared_token,
            "X-Node-Credential":node_credential(),
            "X-Node-ID":NODE_ID,
        }
        if self.http is None:
            raise RuntimeError("micro-event ingest session is not started")
        async with self.http.post(
            settings.coordinator_url+"/ingest/event",
            json=row,
            headers=headers,
        ) as resp:
            if resp.status!=200:
                raise RuntimeError(
                    "CONTROL micro-event ingest rejected: "+str(resp.status)
                )
        await self.spool.ack(record_id)

    def metrics(self):
        m=self.write_queue.metrics()
        m["spool_bytes"]=self.spool.bytes_used()
        m["spool_ratio"]=self.spool.ratio()
        return m
