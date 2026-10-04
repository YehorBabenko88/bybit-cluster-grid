from __future__ import annotations
import asyncio,hashlib,json,os,tempfile
from pathlib import Path
import aiohttp
from .archive_download import download_verified,safe_delete_owned
from .archive_stream_parser import iter_minute_aggregates
from .config import settings
from .content_cache import ContentAddressedCache
from .credential_store import node_credential
from .resources import NODE_ID


def _headers():
    return {"X-Grid-Token":settings.grid_shared_token,"X-Node-Credential":node_credential()}


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


async def archive_compute_loop(stop_event=None,poll_seconds=3):
    if not settings.archive_compute_enabled:return
    stop_event=stop_event or asyncio.Event()
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            job=None
            try:
                async with session.post(settings.coordinator_url+"/compute/archive/claim",
                    json={"node_id":NODE_ID,"lease_seconds":300},headers=_headers(),timeout=15) as r:
                    if r.status!=200:
                        await asyncio.sleep(poll_seconds);continue
                    job=(await r.json()).get("job")
                if not job:
                    await asyncio.sleep(poll_seconds);continue
                manifest=await _execute(job)
                async with session.post(settings.coordinator_url+f"/compute/archive/{job['id']}/result",
                    json={"node_id":NODE_ID,"lease_generation":int(job["lease_generation"]),"manifest":manifest},
                    headers=_headers(),timeout=30) as r:
                    body=await r.text()
                    if r.status!=200:raise RuntimeError(f"archive result rejected {r.status}: {body[:1000]}")
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
