import asyncio
import hashlib
import math
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
        self.replay_error=None
        self.replay_ids=set()
        # Preserve WAL ID order across concurrent producers until queue admission.
        self._enqueue_lock=asyncio.Lock()
        self._last_replay_send=0.0
        self.replay_started_at=0.0
        self.replay_sent=0
        self.replay_rate=float(settings.replay_micro_per_second)
        self.write_queue=BoundedWriteQueue(
            self._save_spooled,
            maxsize=20000,
            workers=1,
        )

    async def start(self):
        self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        await self.write_queue.start()
        pending=self.spool.iter_recover()
        self.replay_error=None
        self.replay_done.clear()
        self.replay_task=asyncio.create_task(self._replay(pending))

    async def _replay(self,pending):
        try:
            self.replay_started_at=asyncio.get_running_loop().time()
            self.replay_sent=0
            # Deterministic node jitter prevents all agents from hammering CONTROL
            # in the same second after a fleet/network outage.
            jitter=max(0.0,float(settings.replay_start_jitter_seconds))
            if jitter:
                seed=int(hashlib.sha256(NODE_ID.encode("utf-8")).hexdigest()[:8],16)
                await asyncio.sleep((seed%10000)/10000.0*jitter)
            for record_id,row in pending:
                self.replay_ids.add(record_id)
                await self.write_queue.put(record_id,row)
            # Recovery is complete only after every recovered WAL record has
            # reached the durable sink and _save_spooled() has ACKed its WAL id.
            await self.write_queue.q.join()
        except (Exception,asyncio.CancelledError) as exc:
            # Wake producers with an explicit failure; never let them overtake
            # incomplete replay or hang indefinitely after replay exits.
            self.replay_error=exc
            self.replay_done.set()
            raise
        else:
            self.replay_done.set()

    async def insert_event(self,symbol,event_ts,event_type,payload):
        await self.replay_done.wait()
        if getattr(self,"replay_error",None) is not None:
            raise RuntimeError("WAL replay failed; restart storage before accepting writes") from self.replay_error
        if self.spool.ratio()>=settings.spool_critical_ratio:
            raise BufferError("Grid micro-event WAL critical threshold reached; load shedding required")
        row={
            "symbol":symbol,
            "event_ts":int(event_ts),
            "event_type":event_type,
            "payload":payload,
        }
        async with self._enqueue_lock:
            if getattr(self,"replay_error",None) is not None:
                raise RuntimeError("WAL replay failed; restart storage before accepting writes") from self.replay_error
            record_id=await self.spool.append(row)
            # Cancellation must not wait for capacity during an outage. Stop
            # admission under the order lock and fail closed so later IDs cannot
            # overtake this durable, unacknowledged record before restart.
            admission=asyncio.create_task(self.write_queue.put(record_id,row))
            try:
                await asyncio.shield(admission)
            except asyncio.CancelledError as exc:
                admission.cancel()
                # Queue.put is cancellation-cooperative; finish its cancellation
                # even if the producer receives repeated cancellation requests.
                while not admission.done():
                    try:
                        await asyncio.shield(admission)
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        break
                # The producer may be cancelled after its child has already
                # admitted the record. That successful admission preserves WAL
                # order and needs no restart. Only failed admission poisons it.
                if admission.cancelled():
                    self.replay_error=exc
                else:
                    failure=admission.exception()
                    if failure is not None:
                        self.replay_error=failure
                raise
            except Exception as exc:
                self.replay_error=exc
                raise


    def set_replay_rate(self,rate):
        try:value=float(rate)
        except (TypeError,ValueError,OverflowError):return
        if math.isfinite(value) and value>=0:
            self.replay_rate=value

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
        if record_id in self.replay_ids:
            rate=float(self.replay_rate)
            while rate<=0:
                await asyncio.sleep(1.0)
                rate=float(self.replay_rate)
            interval=1.0/max(0.1,rate)
            wait=interval-(asyncio.get_running_loop().time()-self._last_replay_send)
            if wait>0: await asyncio.sleep(wait)
            self._last_replay_send=asyncio.get_running_loop().time()

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
        if record_id in self.replay_ids:
            self.replay_sent+=1
        self.replay_ids.discard(record_id)

    def metrics(self):
        m=self.write_queue.metrics()
        m["spool_bytes"]=self.spool.bytes_used()
        m["spool_ratio"]=self.spool.ratio()
        m["replay_failed"]=getattr(self,"replay_error",None) is not None
        m["replay_active"]=not self.replay_done.is_set() or m["replay_failed"]
        m["replay_backlog_bytes"]=m["spool_bytes"] if m["replay_active"] else 0
        m["replay_rate_per_second"]=float(self.replay_rate)
        elapsed=max(0.0,asyncio.get_running_loop().time()-self.replay_started_at) if self.replay_started_at else 0.0
        m["replay_sent"]=int(self.replay_sent)
        m["replay_elapsed_seconds"]=round(elapsed,1)
        m["replay_observed_per_second"]=round(self.replay_sent/elapsed,2) if elapsed>0 else 0.0
        return m
