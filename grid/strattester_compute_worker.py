from __future__ import annotations
import asyncio,hashlib,json,logging,os,shlex,tempfile
from pathlib import Path
import aiohttp
import psutil
from .config import settings
from .credential_store import node_credential
from .content_cache import ContentAddressedCache
from .resources import NODE_ID,snapshot
from .local_operator_gate import compute_locally_enabled

log=logging.getLogger("strattester_compute")


def _headers():
    return {"X-Grid-Token":settings.grid_shared_token,
            "X-Node-Credential":node_credential(),
            "X-Node-ID":NODE_ID}


def _resource_ok():
    s=snapshot()
    rss=psutil.Process().memory_info().rss
    rss_limit=float(settings.worker_process_memory_mb)*1024**2*float(settings.worker_process_memory_backoff_ratio)
    return (compute_locally_enabled()
            and float(s.get("cpu_pct",100))<settings.resource_cpu_limit
            and float(s.get("ram_pct",100))<settings.resource_ram_limit
            and float(s.get("disk_free",0))>=settings.resource_disk_free_gb*1024**3
            and rss<rss_limit)


async def _prepare_dataset_input(session,payload,root):
    spec=dict(payload.get("input_spec") or {})
    if str(payload.get("job_type") or "")!="strategy_backtest" or spec.get("local_market_db"):
        payload["input_spec"]=spec
        return payload
    digest=str(spec.get("dataset_sha256") or "").lower()
    if len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("strategy_backtest requires dataset_sha256 when local_market_db is absent")
    cache=ContentAddressedCache(settings.content_cache_root)
    max_bytes=int(settings.compute_artifact_upload_max_gb*1024**3)
    if not cache.has(digest):
        # A corrupt object at the expected digest is service-owned and safe to evict;
        # the replacement is still accepted only after SHA-256 verification.
        if cache.path_for(digest).exists():
            cache.discard(digest)
        uri=str(spec.get("dataset_uri") or (
            settings.coordinator_url.rstrip("/")+"/compute/artifacts/"+digest))
        headers=_headers() if uri.startswith(settings.coordinator_url.rstrip("/")) else {}
        fd,tmp=tempfile.mkstemp(prefix="grid-dataset-",suffix=".part",dir=root);os.close(fd)
        h=hashlib.sha256()
        try:
            async with session.get(uri,headers=headers,timeout=aiohttp.ClientTimeout(total=None,sock_read=60)) as r:
                if r.status!=200:
                    raise RuntimeError(f"dataset artifact download failed status={r.status}")
                declared=r.headers.get("Content-Length")
                if declared and int(declared)>max_bytes:
                    raise RuntimeError("dataset artifact exceeds worker download limit")
                size=0
                with open(tmp,"wb") as out:
                    async for chunk in r.content.iter_chunked(1024*1024):
                        if not chunk:continue
                        size+=len(chunk)
                        if size>max_bytes:
                            raise RuntimeError("dataset artifact exceeds worker download limit")
                        h.update(chunk);out.write(chunk)
                    out.flush();os.fsync(out.fileno())
            if h.hexdigest()!=digest:
                raise ValueError("dataset artifact sha256 mismatch")
            cache.put(tmp,digest)
        finally:
            try:os.remove(tmp)
            except FileNotFoundError:pass
    market_db=root/"market.db"
    cache.materialize(digest,market_db)
    spec["local_market_db"]=str(market_db)
    spec["local_results_db"]=str(root/"results.db")
    payload["input_spec"]=spec
    return payload


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


async def _terminate_tree(proc):
    try:
        parent=psutil.Process(proc.pid)
        children=parent.children(recursive=True)
        for p in children:
            try:p.terminate()
            except psutil.Error:pass
        try:parent.terminate()
        except psutil.Error:pass
        _,alive=psutil.wait_procs(children+[parent],timeout=5)
        for p in alive:
            try:p.kill()
            except psutil.Error:pass
    except psutil.Error:
        pass
    try:await asyncio.wait_for(proc.wait(),timeout=5)
    except (asyncio.TimeoutError,ProcessLookupError):pass


async def _run_job(session,job):
    job_id=str(job["id"]); generation=int(job["lease_generation"])
    payload=dict(job.get("payload") or {})
    with tempfile.TemporaryDirectory(prefix="grid-strattester-") as td:
        root=Path(td); job_path=root/"job.json"; out_path=root/"result.json"
        payload=await _prepare_dataset_input(session,payload,root)
        job_path.write_text(json.dumps({"payload":payload},sort_keys=True,default=str),encoding="utf-8")
        command=shlex.split(settings.strattester_command,posix=os.name!="nt")
        if not command: raise RuntimeError("empty strattester command")
        proc=await asyncio.create_subprocess_exec(
            *command,"--job",str(job_path),"--output",str(out_path),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,
            creationflags=(0x00000200 if os.name=="nt" else 0),
            start_new_session=(os.name!="nt"))
        lost=asyncio.Event()
        renew=asyncio.create_task(_renew_loop(session,job_id,generation,lost))
        output=[];started=asyncio.get_running_loop().time()
        try:
            while proc.returncode is None:
                try:
                    line=await asyncio.wait_for(proc.stdout.readline(),timeout=1)
                    if line: output.append(line.decode("utf-8","replace"))
                except asyncio.TimeoutError:
                    pass
                rss=0
                try:
                    pp=psutil.Process(proc.pid)
                    rss=pp.memory_info().rss+sum(x.memory_info().rss for x in pp.children(recursive=True))
                except psutil.Error:
                    pass
                if asyncio.get_running_loop().time()-started>int(settings.worker_job_timeout_minutes)*60:
                    await _terminate_tree(proc)
                    raise RuntimeError("strattester wall clock limit exceeded")
                if rss>int(settings.worker_child_memory_mb)*1024**2:
                    await _terminate_tree(proc)
                    raise RuntimeError(f"strattester memory limit exceeded: {rss}")
                if lost.is_set():
                    await _terminate_tree(proc)
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
            if proc.returncode is None:
                await _terminate_tree(proc)


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
                    try:
                        if required and required!=settings.strattester_version:
                            raise ValueError("assigned Strattester version mismatch")
                        await _run_job(session,job)
                    except Exception as exc:
                        text=str(exc)
                        permanent=isinstance(exc,ValueError) or "result rejected status=409" in text or "unsupported Grid job_type" in text
                        try:
                            async with session.post(settings.coordinator_url+f"/compute/strattester/{job['id']}/fail",
                                json={"node_id":NODE_ID,"lease_generation":int(job["lease_generation"]),
                                      "kind":"permanent" if permanent else "retryable","error":text[:4000]},
                                headers=_headers(),timeout=15) as fr:
                                if fr.status not in (200,409):
                                    log.error("strattester failure report rejected",extra={"event":"strattester_fail_report"})
                        except Exception:
                            log.exception("strattester failure report failed",extra={"event":"strattester_fail_report_failed"})
                        raise
                else:
                    await asyncio.sleep(poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("strattester compute loop failed",extra={"event":"strattester_compute_failed"})
                await asyncio.sleep(max(2,poll_seconds))
