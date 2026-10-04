from __future__ import annotations
import asyncio,json,logging,os,shlex,tempfile
from pathlib import Path
import aiohttp
from .config import settings
from .credential_store import node_credential
from .resources import NODE_ID,snapshot

log=logging.getLogger("strattester_compute")


def _headers():
    return {"X-Grid-Token":settings.grid_shared_token,
            "X-Node-Credential":node_credential()}


def _resource_ok():
    s=snapshot()
    return (float(s.get("cpu_pct",100)) < settings.resource_cpu_limit
            and float(s.get("ram_pct",100)) < settings.resource_ram_limit
            and float(s.get("disk_free",0)) >= settings.resource_disk_free_gb*1024**3)


async def _renew_loop(session,job_id,generation,lost,period=40):
    while not lost.is_set():
        await asyncio.sleep(period)
        try:
            async with session.post(settings.coordinator_url+f"/compute/strattester/{job_id}/renew",
                json={"node_id":NODE_ID,"lease_generation":generation,"lease_seconds":120},
                headers=_headers(),timeout=15) as r:
                if r.status!=200:
                    lost.set();return
        except Exception:
            # A transient network failure does not immediately kill the child; the
            # next renewal decides. CONTROL fencing rejects late completion anyway.
            log.exception("strattester lease renewal failed",extra={"event":"strattester_renew_failed"})


async def _run_job(session,job):
    job_id=str(job["id"]); generation=int(job["lease_generation"])
    payload=dict(job.get("payload") or {})
    with tempfile.TemporaryDirectory(prefix="grid-strattester-") as td:
        root=Path(td); job_path=root/"job.json"; out_path=root/"result.json"
        job_path.write_text(json.dumps({"payload":payload},sort_keys=True,default=str),encoding="utf-8")
        command=shlex.split(settings.strattester_command,posix=os.name!="nt")
        if not command: raise RuntimeError("empty strattester command")
        proc=await asyncio.create_subprocess_exec(
            *command,"--job",str(job_path),"--output",str(out_path),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        lost=asyncio.Event()
        renew=asyncio.create_task(_renew_loop(session,job_id,generation,lost))
        output=[]
        try:
            while proc.returncode is None:
                try:
                    line=await asyncio.wait_for(proc.stdout.readline(),timeout=1)
                    if line: output.append(line.decode("utf-8","replace"))
                except asyncio.TimeoutError:
                    pass
                if lost.is_set():
                    proc.terminate()
                    await proc.wait()
                    raise RuntimeError("strattester lease lost")
                if proc.returncode is None:
                    try: await asyncio.wait_for(proc.wait(),timeout=0.01)
                    except asyncio.TimeoutError: pass
            if proc.returncode:
                raise RuntimeError(f"strattester rc={proc.returncode}: {''.join(output)[-4000:]}")
            if not out_path.exists(): raise RuntimeError("strattester completed without result manifest")
            manifest=json.loads(out_path.read_text(encoding="utf-8"))
            async with session.post(settings.coordinator_url+f"/compute/strattester/{job_id}/result",
                json={"node_id":NODE_ID,"lease_generation":generation,"manifest":manifest},
                headers=_headers(),timeout=30) as r:
                body=await r.text()
                if r.status!=200: raise RuntimeError(f"result rejected status={r.status}: {body[:1000]}")
        finally:
            lost.set();renew.cancel()
            await asyncio.gather(renew,return_exceptions=True)


async def strattester_compute_loop(stop_event=None,poll_seconds=3):
    if not settings.strattester_enabled:return
    if not settings.strattester_version or not settings.strattester_command:
        log.error("Strattester enabled without version/command",extra={"event":"strattester_config_invalid"})
        return
    stop_event=stop_event or asyncio.Event()
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            try:
                if not _resource_ok():
                    await asyncio.sleep(max(5,poll_seconds));continue
                async with session.post(settings.coordinator_url+"/compute/strattester/claim",
                    json={"node_id":NODE_ID,"lease_seconds":120},headers=_headers(),timeout=15) as r:
                    if r.status!=200:
                        await asyncio.sleep(poll_seconds);continue
                    job=(await r.json()).get("job")
                if job:
                    required=str((job.get("payload") or {}).get("strattester_version") or "")
                    if required and required!=settings.strattester_version:
                        raise RuntimeError("assigned Strattester version mismatch")
                    await _run_job(session,job)
                else:
                    await asyncio.sleep(poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("strattester compute loop failed",extra={"event":"strattester_compute_failed"})
                await asyncio.sleep(max(2,poll_seconds))
