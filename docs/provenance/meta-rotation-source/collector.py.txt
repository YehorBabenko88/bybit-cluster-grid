"""Read-only service orchestration. Explicitly avoids using aggregated MetaScalp trades for POC."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from .exchange import BybitPublic
from .instruments import instruments
from .pipeline import RawPipeline

LOG=logging.getLogger(__name__)

class CollectorService:
    def __init__(self, store, on_closed=None, refresh_seconds=300):
        self.store=store
        self.exchange=BybitPublic()
        self.on_closed=on_closed
        self.refresh_seconds=refresh_seconds
        self.pipeline=None
        self.running=False
        self.current=()
        self.refresh_errors=0

    async def run(self):
        self.running=True
        try:
            while self.running:
                try:
                    metadata=await instruments(self.exchange)
                    now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
                    cutoff=now_ms-int(timedelta(days=30).total_seconds()*1000)
                    eligible={s:meta for s,meta in metadata.items() if meta.launch_ms <= cutoff}
                    # Rank the entire market before taking the first 20 eligible symbols.
                    # Otherwise recently listed instruments can crowd out older ones.
                    ranked=await self.exchange.top_volatile(len(metadata))
                    selected=tuple(s for s in ranked if s in eligible)[:20]
                    if not selected:
                        raise RuntimeError("No eligible instruments with validated tick sizes")
                    if selected != self.current:
                        replacement=RawPipeline(self.store,
                            {s:metadata[s].tick_size for s in selected},self.on_closed)
                        await replacement.start()
                        previous=self.pipeline
                        self.pipeline=replacement
                        self.current=selected
                        if previous:
                            await previous.stop()
                        LOG.info("Subscribed to %d validated instruments",len(selected))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.refresh_errors += 1
                    LOG.exception("Collector refresh failed; existing stream preserved")
                await asyncio.sleep(self.refresh_seconds)
        finally:
            if self.pipeline:
                await self.pipeline.stop()
            await self.exchange.close()

    def stop(self):
        self.running=False
