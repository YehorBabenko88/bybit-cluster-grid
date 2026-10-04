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
        self.session=None
        self.write_queue=BoundedWriteQueue(
            self._save_spooled,
            maxsize=20000,
            workers=1,
        )

    async def start(self):
        if self.session is None or self.session.closed:
            self.session=aiohttp.ClientSession()
        await self.write_queue.start()
        for record_id,row in self.spool.recover():
            await self.write_queue.put(record_id,row)

    async def insert_event(self,symbol,event_ts,event_type,payload):
        row={
            "symbol":symbol,
            "event_ts":int(event_ts),
            "event_type":event_type,
            "payload":payload,
        }
        record_id=await self.spool.append(row)
        await self.write_queue.put(record_id,row)

    async def _save_spooled(self,record_id,row):
        from .credential_store import node_credential

        headers={
            "X-Grid-Token":settings.grid_shared_token,
            "X-Node-Credential":node_credential(),
            "X-Node-ID":NODE_ID,
        }
        if self.session is None or self.session.closed:
            self.session=aiohttp.ClientSession()
        async with self.session.post(
                settings.coordinator_url+"/ingest/event",
                json=row,
                headers=headers,
                timeout=20,
            ) as resp:
                if resp.status!=200:
                    raise RuntimeError(
                        "CONTROL micro-event ingest rejected: "+str(resp.status)
                    )
        await self.spool.ack(record_id)

    async def close(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()

    def metrics(self):
        m=self.write_queue.metrics()
        m["spool_bytes"]=self.spool.bytes_used()
        m["spool_ratio"]=self.spool.ratio()
        return m
