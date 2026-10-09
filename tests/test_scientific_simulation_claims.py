import asyncio
from grid.scientific_simulation_gate import ScientificSimulationGate


class ClaimPool:
    def __init__(self):
        self.remaining=[{"id":"one","hypothesis_id":"hyp","dataset_cutoff":"cutoff"}]
        self.queries=[]

    async def fetchrow(self,query,*args):
        self.queries.append(query)
        if "SKIP LOCKED" in query:
            return self.remaining.pop(0) if self.remaining else None
        return None


def test_scientific_queue_claims_jobs_atomically():
    class Gate(ScientificSimulationGate):
        async def run_one(self,run_id,hypothesis_id,dataset_cutoff,claimed=False):
            assert claimed is True
            return {"run_id":run_id,"status":"SIMULATION_FAILED"}

    async def scenario():
        pool=ClaimPool()
        first,second=await asyncio.gather(Gate(pool).run_queued(),Gate(pool).run_queued())
        assert sum(len(x) for x in (first,second))==1
        assert all("FOR UPDATE SKIP LOCKED" in q for q in pool.queries)
    asyncio.run(scenario())


def test_direct_scientific_run_rejects_unclaimed_job():
    class Gate(ScientificSimulationGate):
        pass

    async def scenario():
        pool=ClaimPool()
        result=await Gate(pool).run_one("already-running","hyp","cutoff")
        assert result["status"]=="NOT_CLAIMED"
    asyncio.run(scenario())
