import json
from .ml_resource_scheduler import Workload,choose_node
from .ml_reservations import reserved_by_node

WORKLOAD_DEFAULTS={
 "dataset":{"cpu":1.0,"ram_gb":4,"scratch_gb":10},
 "train":{"cpu":4.0,"ram_gb":8,"scratch_gb":10},
 "backtest":{"cpu":3.0,"ram_gb":4,"scratch_gb":5},
 "evaluate":{"cpu":2.0,"ram_gb":3,"scratch_gb":3},
}
# Stable project-wide advisory lock, not a per-process Python mutex.
# Lock scope is one PostgreSQL transaction and is released on rollback/crash.
DISPATCH_LOCK_KEY=734106028

def _job_payload(value):
    """asyncpg returns jsonb as text unless a custom codec is installed."""
    if value is None:
        return {}
    if isinstance(value,str):
        value=json.loads(value)
    if not isinstance(value,dict):
        raise ValueError("ML job payload must be a JSON object")
    return value

def _adjust_nodes(nodes,reservations):
    adjusted={}
    for node_id,n in nodes.items():
        try:
            x=dict(n); r=reservations.get(node_id,{})
            x["ram_available"]=max(0,float(x.get("ram_available",0))-float(r.get("ram_gb",0) or 0)*1024**3)
            x["disk_free"]=max(0,float(x.get("disk_free",0))-float(r.get("scratch_gb",0) or 0)*1024**3)
            cpu_count=max(1,int(x.get("cpu_count",1)))
            x["cpu_pct"]=min(100.0,float(x.get("cpu_pct",0))+100.0*float(r.get("cpu",0) or 0)/cpu_count)
            if r.get("gpu"):
                x["gpu_available"]=False
        except (TypeError,ValueError,OverflowError):
            continue
        adjusted[node_id]=x
    return adjusted

class MLDispatcher:
    def __init__(self,pool,node_provider):
        self.pool=pool; self.node_provider=node_provider

    async def __call__(self,slots,health=None,leader_owner=None):
        # Read node telemetry after acquiring the dispatch lock, so a waiting
        # coordinator does not schedule against a pre-lock snapshot.
        dispatched=[]
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("SELECT pg_advisory_xact_lock($1)",DISPATCH_LOCK_KEY)
                if leader_owner is not None:
                    # Lock the leadership row until this dispatch transaction
                    # commits. A takeover must wait; an expired leader cannot
                    # assign any work after the row lock becomes available.
                    leader=await c.fetchval("""SELECT 1 FROM service_leases
                      WHERE service_key='ml-orchestrator-leader' AND owner=$1
                        AND lease_until>clock_timestamp() FOR UPDATE""",leader_owner)
                    if leader!=1:
                        return []
                reported=await self.node_provider()
                reservations=await reserved_by_node(c)
                nodes=_adjust_nodes(reported,reservations)
                active=await c.fetchval("""SELECT count(*) FROM ml_jobs
                  WHERE status IN ('assigned','running') AND lease_until>=clock_timestamp()""")
                budget=max(0,int(slots)-int(active or 0))
                for _ in range(budget):
                    jobs=await c.fetch("""SELECT * FROM ml_jobs WHERE status='queued'
                      AND attempts<max_attempts AND (not_before IS NULL OR not_before<=clock_timestamp())
                      ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 32""")
                    if not jobs: break
                    job=None;pick=None;w=None
                    for candidate in jobs:
                        try:
                            payload=_job_payload(candidate["payload"])
                            d=WORKLOAD_DEFAULTS.get(candidate["job_type"],WORKLOAD_DEFAULTS["evaluate"])
                            candidate_nodes=nodes
                            if candidate["job_type"] in ("train","evaluate"):
                                candidate_nodes={k:v for k,v in nodes.items() if v.get("ml_runtime_ready") is True}
                                if not candidate_nodes:continue
                            w=Workload(candidate["job_type"],cpu=float(payload.get("cpu",d["cpu"])),
                              ram_gb=float(payload.get("ram_gb",d["ram_gb"])),
                              scratch_gb=float(payload.get("scratch_gb",d["scratch_gb"])),
                              input_gb=float(payload.get("input_gb",0)),
                              gpu=bool(payload.get("gpu",False)),data_locality=payload.get("data_locality"))
                            pick=choose_node(candidate_nodes,w)
                        except (TypeError,ValueError,OverflowError):
                            continue
                        if pick:
                            job=candidate;break
                    if not job:break
                    _,node_id,why=pick
                    changed=await c.execute("""UPDATE ml_jobs SET status='assigned',lease_owner=$2,
                      lease_until=clock_timestamp()+interval '2 minutes' WHERE id=$1 AND status='queued'""",
                      job["id"],node_id)
                    if not changed.endswith(" 1"):continue
                    await c.execute("""INSERT INTO ml_resource_reservations
                      (job_id,node_id,cpu,ram_gb,scratch_gb,gpu,expires_at)
                      VALUES($1,$2,$3,$4,$5,$6,clock_timestamp()+interval '2 minutes')
                      ON CONFLICT(job_id) DO UPDATE SET node_id=EXCLUDED.node_id,cpu=EXCLUDED.cpu,
                      ram_gb=EXCLUDED.ram_gb,scratch_gb=EXCLUDED.scratch_gb,gpu=EXCLUDED.gpu,
                      expires_at=EXCLUDED.expires_at""",job["id"],node_id,w.cpu,w.ram_gb,w.scratch_gb,w.gpu)
                    selected=nodes[node_id]
                    selected["ram_available"]=max(0.0,float(selected.get("ram_available",0))-w.ram_gb*1024**3)
                    selected["disk_free"]=max(0.0,float(selected.get("disk_free",0))-w.scratch_gb*1024**3)
                    cores=max(1,int(selected.get("cpu_count",1)))
                    selected["cpu_pct"]=min(100.0,float(selected.get("cpu_pct",0))+100.0*w.cpu/cores)
                    if w.gpu:selected["gpu_available"]=False
                    dispatched.append({"job_id":str(job["id"]),"node_id":node_id,"placement":why})
        return dispatched
