from __future__ import annotations
import asyncio,hashlib,json,os,tempfile
from pathlib import Path
import aiohttp
from .archive_download import download_verified,safe_delete_owned
from .archive_stream_parser import iter_minute_aggregates
from .config import settings
from .content_cache import ContentAddressedCache
from .credential_store import node_credential
from .resources import NODE_ID,snapshot


def _headers():
    return {"X-Grid-Token":settings.grid_shared_token,"X-Node-Credential":node_credential()}


async def _renew_loop(session,job,lost,period=90):
    while not lost.is_set():
        await asyncio.sleep(period)
        try:
            async with session.post(settings.coordinator_url+f"/compute/archive/{job['id']}/renew",
                json={"node_id":NODE_ID,"lease_generation":int(job["lease_generation"]),"lease_seconds":300},
                headers=_headers(),timeout=15) as r:
                if r.status!=200:
                    lost.set();return
        except Exception:
            # CONTROL still fences late results. A later renewal may recover a transient outage.
            pass


async def _execute(job):
    cache=ContentAddressedCache(settings.content_cache_root)
    with tempfile.TemporaryDirectory(prefix="grid-archive-compute-") as td:
        dl=await download_verified(job["source_uri"],td,job.get("expected_sha256"),job.get("expected_bytes"))
        cached=cache.put(dl["path"],dl["sha256"])
        source_rows=candles=levels=0;min_ts=max_ts=None
        for row in iter_minute_aggregates(cached["path"],job["symbol"],float(job["tick_size"])):
            candles+=1;levels+=len(row["levels"]);source_rows+=int(row["trade_count"])
            ts=row["ts"];min_ts=ts if min_ts is None else min(min_ts,ts);max_ts=ts if max_ts is None else max(max_ts,ts)
        return {"symbol":job["symbol"],"archive_date":str(job["archive_date"]),
                "source_uri":job["source_uri"],"tick_size":float(job["tick_size"]),
                "source_sha256":dl["sha256"],"source_bytes":dl["bytes"],
                "cache_sha256":cached["sha256"],"source_rows":source_rows,
                "derived_candles":candles,"derived_footprint_rows":levels,
                "min_ts":str(min_ts) if min_ts else None,"max_ts":str(max_ts) if max_ts else None}


def _resource_ok():
    s=snapshot()
    return (float(s.get("cpu_pct",100))<settings.resource_cpu_limit
            and float(s.get("ram_pct",100))<settings.resource_ram_limit
            and float(s.get("disk_free",0))>=settings.resource_disk_free_gb*1024**3)


async def archive_compute_loop(stop_event=None,poll_seconds=3):
    if not settings.archive_compute_enabled:return
    stop_event=stop_event or asyncio.Event()
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            job=None
            try:
                if not _resource_ok():
                    await asyncio.sleep(max(5,poll_seconds));continue
                async with session.post(settings.coordinator_url+"/compute/archive/claim",
                    json={"node_id":NODE_ID,"lease_seconds":300},headers=_headers(),timeout=15) as r:
                    if r.status!=200:
                        await asyncio.sleep(poll_seconds);continue
                    job=(await r.json()).get("job")
                if not job:
                    await asyncio.sleep(poll_seconds);continue
                lost=asyncio.Event()
                renew=asyncio.create_task(_renew_loop(session,job,lost))
                try:
                    manifest=await _execute(job)
                    if lost.is_set():raise RuntimeError("archive compute lease lost")
                    async with session.post(settings.coordinator_url+f"/compute/archive/{job['id']}/result",
                        json={"node_id":NODE_ID,"lease_generation":int(job["lease_generation"]),"manifest":manifest},
                        headers=_headers(),timeout=30) as r:
                        body=await r.text()
                        if r.status!=200:raise RuntimeError(f"archive result rejected {r.status}: {body[:1000]}")
                finally:
                    lost.set();renew.cancel()
                    await asyncio.gather(renew,return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if job:
                    try:
                        async with session.post(settings.coordinator_url+f"/compute/archive/{job['id']}/fail",
                            json={"node_id":NODE_ID,"lease_generation":int(job["lease_generation"]),"error":str(exc)[:4000]},
                            headers=_headers(),timeout=15):
                            pass
                    except Exception:
                        pass
                await asyncio.sleep(max(2,poll_seconds))
