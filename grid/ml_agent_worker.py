import asyncio,hashlib,json,os,pathlib,shutil,sys,tempfile,time
from .config import settings
from .ml_process_supervisor import run_supervised_process
from .ml_remote_lease import run_remote_lease


def verify_dataset_bundle(dataset):
    samples=list(dataset.get("samples") or [])
    if len(samples)!=int(dataset.get("sample_count",-1)):
        raise ValueError("dataset sample count mismatch")
    hashes=[]
    for row in samples:
        canonical=json.dumps(row,sort_keys=True,default=str,separators=(",",":"))
        hashes.append(hashlib.sha256(canonical.encode()).hexdigest())
    digest=hashlib.sha256("\n".join(hashes).encode()).hexdigest()
    if digest!=dataset.get("dataset_hash"):
        raise ValueError("dataset hash mismatch")
    return digest


def _workspace_root():
    base=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"/"ml-work"
    base.mkdir(parents=True,exist_ok=True)
    return base

def cleanup_stale_workspaces(older_than_seconds=86400):
    root=_workspace_root();cutoff=time.time()-max(3600,int(older_than_seconds));removed=0
    for p in root.glob("job-*"):
        try:
            if p.is_dir() and p.stat().st_mtime<cutoff:
                shutil.rmtree(p,ignore_errors=True);removed+=1
        except OSError:pass
    return removed


async def _write_paged_bundle(client,job,bundle_path,page_size=500):
    if int(page_size)<=0:
        raise ValueError("dataset page size must be positive")
    first=await client.dataset_page(job,0,page_size)
    if first is None:raise RuntimeError("remote ML lease lost before dataset fetch")
    total=int(first.get("sample_count",0))
    if total<=0:
        raise ValueError("dataset sample count must be positive")
    expected=first.get("dataset_hash")
    count=0;offset=0;agg=hashlib.sha256();first_hash=True;first_sample=True
    with open(bundle_path,"w",encoding="utf-8") as f:
        f.write('{"job":')
        f.write(json.dumps(job,separators=(",",":"),default=str))
        f.write(',"dataset":{"dataset_id":')
        f.write(json.dumps(first["dataset_id"]))
        f.write(',"dataset_hash":')
        f.write(json.dumps(expected))
        f.write(',"feature_version":')
        f.write(json.dumps(first.get("feature_version")))
        f.write(',"sample_count":')
        f.write(str(total))
        f.write(',"samples":[')
        while offset<total:
            page=first if offset==0 else await client.dataset_page(job,offset,page_size)
            if page is None:raise RuntimeError("remote ML lease lost during dataset fetch")
            if (page.get("dataset_id")!=first.get("dataset_id") or
                    page.get("dataset_hash")!=expected or
                    int(page.get("sample_count",-1))!=total or
                    page.get("feature_version")!=first.get("feature_version")):
                raise ValueError("dataset page metadata changed during transfer")
            items=list(page.get("samples") or [])
            if not items:break
            if len(items)>min(int(page_size),total-offset):
                raise ValueError("dataset page exceeds remaining sample count")
            for item in items:
                payload=item["payload"]
                canonical=json.dumps(payload,sort_keys=True,default=str,separators=(",",":"))
                digest=hashlib.sha256(canonical.encode()).hexdigest()
                if digest!=item.get("payload_hash"):raise ValueError("dataset payload hash mismatch")
                if not first_hash:agg.update(b"\n")
                agg.update(digest.encode());first_hash=False
                if not first_sample:f.write(",")
                f.write(json.dumps(payload,separators=(",",":"),default=str))
                first_sample=False;count+=1
            offset+=len(items)
            if await client.renew(job) is None:
                raise RuntimeError("remote ML lease lost during dataset transfer")
        f.write("]}}")
        f.flush();os.fsync(f.fileno())
    if count!=total:raise ValueError("dataset sample count mismatch")
    if agg.hexdigest()!=expected:raise ValueError("dataset hash mismatch")
    return {"sample_count":count,"dataset_hash":expected}

def _file_sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()

async def execute_remote_job(client,job):
    if job.get("job_type")!="train":raise ValueError("unsupported remote ML job type")
    payload=dict(job.get("payload") or {})
    timeout=max(60,min(int(payload.get("timeout_seconds",settings.ml_job_timeout_seconds)),
                       int(settings.ml_job_timeout_seconds)))
    ram=max(256,min(int(payload.get("ram_limit_mb",settings.ml_job_ram_limit_mb)),
                    int(settings.ml_job_ram_limit_mb)))
    workdir=pathlib.Path(tempfile.mkdtemp(prefix="job-",dir=str(_workspace_root())))
    bundle=workdir/"bundle.json";artifact=workdir/"artifact.bin";result=workdir/"result.json"
    try:
        await _write_paged_bundle(client,job,bundle)
        argv=[sys.executable,"-m","grid.ml_compute_entry","--bundle",str(bundle),
              "--artifact",str(artifact),"--result",str(result)]
        async def work():
            return await run_supervised_process(argv,timeout_seconds=timeout,ram_limit_mb=ram,
                                                poll_seconds=.5,grace_seconds=5,env=os.environ.copy())
        await run_remote_lease(client,job,work,renew_every=30)
        sha=_file_sha256(artifact)
        uploaded=await client.artifact_file(job,artifact,sha)
        if uploaded is None:raise RuntimeError("remote ML lease lost before artifact upload")
        metrics=json.loads(result.read_text(encoding="utf-8")).get("metrics") or {}
        final=await client.finalize(job,uploaded["artifact_id"],metrics)
        if final is None:raise RuntimeError("remote ML lease lost before finalize")
        return final
    finally:
        shutil.rmtree(workdir,ignore_errors=True)


async def ml_agent_loop(client,stop_event=None,poll_seconds=5,can_claim=None):
    stop_event=stop_event or asyncio.Event()
    cleanup_stale_workspaces()
    while not stop_event.is_set():
        if can_claim is not None and not can_claim():
            try:await asyncio.wait_for(stop_event.wait(),timeout=float(poll_seconds))
            except asyncio.TimeoutError:pass
            continue
        try:
            job=await client.claim()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Transient CONTROL/network failures must not permanently kill the
            # ML poller. No lease has been acquired at this point.
            try:await asyncio.wait_for(stop_event.wait(),timeout=max(1.0,float(poll_seconds)))
            except asyncio.TimeoutError:pass
            continue
        if not job:
            try:await asyncio.wait_for(stop_event.wait(),timeout=float(poll_seconds))
            except asyncio.TimeoutError:pass
            continue
        try:
            await execute_remote_job(client,job)
        except asyncio.CancelledError:
            raise
        except Exception:
            # CONTROL lease expiry/retry owns recovery. Do not invent a second
            # failure state machine on the DB-less node.
            try:await asyncio.wait_for(stop_event.wait(),timeout=min(5,float(poll_seconds)))
            except asyncio.TimeoutError:pass
