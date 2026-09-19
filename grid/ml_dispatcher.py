import json,uuid
from .ml_resource_scheduler import Workload,choose_node

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
        active=await self.pool.fetchval("""SELECT count(*) FROM ml_jobs
          WHERE status='running' AND lease_until>=now()""")
        budget=max(0,int(slots)-int(active or 0)); dispatched=[]
        for _ in range(budget):
            async with self.pool.acquire() as c:
                async with c.transaction():
                    job=await c.fetchrow("""SELECT * FROM ml_jobs WHERE status='queued'
                      ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
                    if not job: break
                    payload=dict(job["payload"] or {})
                    d=WORKLOAD_DEFAULTS.get(job["job_type"],WORKLOAD_DEFAULTS["evaluate"])
                    w=Workload(job["job_type"],cpu=float(payload.get("cpu",d["cpu"])),
                      ram_gb=float(payload.get("ram_gb",d["ram_gb"])),
                      scratch_gb=float(payload.get("scratch_gb",d["scratch_gb"])),
                      input_gb=float(payload.get("input_gb",0)),
                      gpu=bool(payload.get("gpu",False)),data_locality=payload.get("data_locality"))
                    pick=choose_node(nodes,w)
                    if not pick: break
                    _,node_id,why=pick
                    await c.execute("""UPDATE ml_jobs SET status='assigned',lease_owner=$2,
                      lease_until=now()+interval '2 minutes' WHERE id=$1 AND status='queued'""",
                      job["id"],node_id)
                    dispatched.append({"job_id":str(job["id"]),"node_id":node_id,"placement":why})
        return dispatched
