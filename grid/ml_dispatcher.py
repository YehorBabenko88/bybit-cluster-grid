import json,uuid
from .ml_resource_scheduler import Workload,choose_node
from .ml_reservations import reserved_by_node

WORKLOAD_DEFAULTS={
 "dataset":{"cpu":1.0,"ram_gb":4,"scratch_gb":10},
 "train":{"cpu":4.0,"ram_gb":8,"scratch_gb":10},
 "backtest":{"cpu":3.0,"ram_gb":4,"scratch_gb":5},
 "evaluate":{"cpu":2.0,"ram_gb":3,"scratch_gb":3},
}

class MLDispatcher:
    def __init__(self,pool,node_provider):
        self.pool=pool; self.node_provider=node_provider

    async def __call__(self,slots,health=None):
        nodes=await self.node_provider()
        reservations=await reserved_by_node(self.pool)
        adjusted={}
        for node_id,n in nodes.items():
            x=dict(n); r=reservations.get(node_id,{})
            x["ram_available"]=max(0,float(x.get("ram_available",0))-float(r.get("ram_gb",0) or 0)*1024**3)
            x["disk_free"]=max(0,float(x.get("disk_free",0))-float(r.get("scratch_gb",0) or 0)*1024**3)
            cpu_count=max(1,int(x.get("cpu_count",1)))
            x["cpu_pct"]=min(100.0,float(x.get("cpu_pct",0))+100.0*float(r.get("cpu",0) or 0)/cpu_count)
            adjusted[node_id]=x
        nodes=adjusted
        active=await self.pool.fetchval("""SELECT count(*) FROM ml_jobs
          WHERE status IN ('assigned','running') AND lease_until>=now()""")
        budget=max(0,int(slots)-int(active or 0)); dispatched=[]
        for _ in range(budget):
            async with self.pool.acquire() as c:
                async with c.transaction():
                    jobs=await c.fetch("""SELECT * FROM ml_jobs WHERE status='queued'
                      AND attempts<max_attempts AND (not_before IS NULL OR not_before<=now())
                      ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 32""")
                    if not jobs: break
                    job=None;pick=None
                    for candidate in jobs:
                        payload=dict(candidate["payload"] or {})
                        d=WORKLOAD_DEFAULTS.get(candidate["job_type"],WORKLOAD_DEFAULTS["evaluate"])
                        w=Workload(candidate["job_type"],cpu=float(payload.get("cpu",d["cpu"])),
                          ram_gb=float(payload.get("ram_gb",d["ram_gb"])),
                          scratch_gb=float(payload.get("scratch_gb",d["scratch_gb"])),
                          input_gb=float(payload.get("input_gb",0)),
                          gpu=bool(payload.get("gpu",False)),data_locality=payload.get("data_locality"))
                        pick=choose_node(nodes,w)
                        if pick:
                            job=candidate;break
                    if not job: break
                    _,node_id,why=pick
                    changed=await c.execute("""UPDATE ml_jobs SET status='assigned',lease_owner=$2,
                      lease_until=now()+interval '2 minutes' WHERE id=$1 AND status='queued'""",
                      job["id"],node_id)
                    if not changed.endswith(" 1"): continue
                    await c.execute("""INSERT INTO ml_resource_reservations
                      (job_id,node_id,cpu,ram_gb,scratch_gb,gpu,expires_at)
                      VALUES($1,$2,$3,$4,$5,$6,now()+interval '2 minutes')
                      ON CONFLICT(job_id) DO UPDATE SET node_id=EXCLUDED.node_id,cpu=EXCLUDED.cpu,
                      ram_gb=EXCLUDED.ram_gb,scratch_gb=EXCLUDED.scratch_gb,gpu=EXCLUDED.gpu,
                      expires_at=EXCLUDED.expires_at""",job["id"],node_id,w.cpu,w.ram_gb,w.scratch_gb,w.gpu)
                    dispatched.append({"job_id":str(job["id"]),"node_id":node_id,"placement":why})
        return dispatched
