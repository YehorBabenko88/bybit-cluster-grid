import asyncio,hashlib,json,os,pathlib,shutil,sys,tempfile
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


async def execute_remote_job(client,job):
    if job.get("job_type")!="train":raise ValueError("unsupported remote ML job type")
    dataset=await client.dataset(job)
    if dataset is None:raise RuntimeError("remote ML lease lost before dataset fetch")
    verify_dataset_bundle(dataset)
    payload=dict(job.get("payload") or {})
    timeout=max(60,min(int(payload.get("timeout_seconds",settings.ml_job_timeout_seconds)),
                       int(settings.ml_job_timeout_seconds)))
    ram=max(256,min(int(payload.get("ram_limit_mb",settings.ml_job_ram_limit_mb)),
                    int(settings.ml_job_ram_limit_mb)))
    workdir=pathlib.Path(tempfile.mkdtemp(prefix="job-",dir=str(_workspace_root())))
    bundle=workdir/"bundle.json";artifact=workdir/"artifact.bin";result=workdir/"result.json"
    try:
        bundle.write_text(json.dumps({"job":job,"dataset":dataset},separators=(",",":"),default=str),encoding="utf-8")
        argv=[sys.executable,"-m","grid.ml_compute_entry","--bundle",str(bundle),
              "--artifact",str(artifact),"--result",str(result)]
        async def work():
            return await run_supervised_process(argv,timeout_seconds=timeout,ram_limit_mb=ram,
                                                poll_seconds=.5,grace_seconds=5,env=os.environ.copy())
        await run_remote_lease(client,job,work,renew_every=30)
        data=artifact.read_bytes()
        sha=hashlib.sha256(data).hexdigest()
        uploaded=await client.artifact(job,data,sha)
        if uploaded is None:raise RuntimeError("remote ML lease lost before artifact upload")
        metrics=json.loads(result.read_text(encoding="utf-8")).get("metrics") or {}
        final=await client.finalize(job,uploaded["artifact_id"],metrics)
        if final is None:raise RuntimeError("remote ML lease lost before finalize")
        return final
    finally:
        shutil.rmtree(workdir,ignore_errors=True)


async def ml_agent_loop(client,stop_event=None,poll_seconds=5,can_claim=None):
    stop_event=stop_event or asyncio.Event()
    while not stop_event.is_set():
        if can_claim is not None and not can_claim():
            try:await asyncio.wait_for(stop_event.wait(),timeout=float(poll_seconds))
            except asyncio.TimeoutError:pass
            continue
        job=await client.claim()
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
