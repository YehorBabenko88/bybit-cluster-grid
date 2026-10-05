import asyncio,json,os,sys
from .config import settings
from .ml_process_supervisor import run_supervised_process
from .ml_worker_protocol import accept_assigned_job,complete_running_job,fail_running_job,run_with_lease


def _job_json(job):
    d=dict(job)
    for k,v in list(d.items()):
        if hasattr(v,"isoformat"):d[k]=v.isoformat()
        elif not isinstance(v,(str,int,float,bool,type(None),dict,list)):
            d[k]=str(v)
    return json.dumps(d,separators=(",",":"))


async def execute_assigned_job(pool,job,node_id):
    payload=dict(job["payload"] or {})
    if job["job_type"]!="train":
        raise ValueError("unsupported ML compute job type")
    timeout=max(60,min(int(payload.get("timeout_seconds",settings.ml_job_timeout_seconds)),
                       int(settings.ml_job_timeout_seconds)))
    ram=max(256,min(int(payload.get("ram_limit_mb",settings.ml_job_ram_limit_mb)),
                        int(settings.ml_job_ram_limit_mb)))
    argv=[sys.executable,"-m","grid.ml_compute_entry","--job-json",_job_json(job)]
    async def work():
        return await run_supervised_process(argv,timeout_seconds=timeout,ram_limit_mb=ram,
                                            poll_seconds=.5,grace_seconds=5,env=os.environ.copy())
    return await run_with_lease(pool,job,node_id,work,lease_seconds=120,renew_every=30)


async def ml_compute_worker(pool,node_id,stop_event=None,poll_seconds=2):
    stop_event=stop_event or asyncio.Event()
    while not stop_event.is_set():
        job=await accept_assigned_job(pool,node_id)
        if not job:
            try:await asyncio.wait_for(stop_event.wait(),timeout=float(poll_seconds))
            except asyncio.TimeoutError:pass
            continue
        generation=int(job["lease_generation"])
        try:
            await execute_assigned_job(pool,job,node_id)
            await complete_running_job(pool,job["id"],node_id,generation)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await fail_running_job(pool,job["id"],node_id,generation,exc)
