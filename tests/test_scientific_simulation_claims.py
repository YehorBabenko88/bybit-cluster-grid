import asyncio
from grid.scientific_simulation_gate import ScientificSimulationGate


class ClaimPool:
    def __init__(self):
        self.remaining=[{"id":"one","hypothesis_id":"hyp","dataset_cutoff":"cutoff","lease_token":"token"}]
        self.queries=[]

    async def fetchval(self,query,*args):
        return None

    async def execute(self,query,*args):
        self.queries.append(query)
        return "UPDATE 0"

    async def fetchrow(self,query,*args):
        self.queries.append(query)
        if "SKIP LOCKED" in query:
            return self.remaining.pop(0) if self.remaining else None
        return None


def test_scientific_queue_claims_jobs_atomically():
    class Gate(ScientificSimulationGate):
        async def run_one(self,run_id,hypothesis_id,dataset_cutoff,claimed=False,lease_token=None):
            assert claimed is True
            return {"run_id":run_id,"status":"SIMULATION_FAILED"}

    async def scenario():
        pool=ClaimPool()
        first,second=await asyncio.gather(Gate(pool).run_queued(),Gate(pool).run_queued())
        assert sum(len(x) for x in (first,second))==1
        assert sum("FOR UPDATE SKIP LOCKED" in q for q in pool.queries)>=2
    asyncio.run(scenario())


def test_direct_scientific_run_rejects_unclaimed_job():
    class Gate(ScientificSimulationGate):
        pass

    async def scenario():
        pool=ClaimPool()
        result=await Gate(pool).run_one("already-running","hyp","cutoff")
        assert result["status"]=="NOT_CLAIMED"
    asyncio.run(scenario())


def test_scientific_lease_recovery_is_bounded_and_migrated():
    from grid.migrations import MIGRATIONS
    migration=next(sqls for version,_,sqls in MIGRATIONS if version==47)
    sql=" ".join(migration)
    assert "lease_token" in sql and "lease_expires_at" in sql and "attempts" in sql
    async def scenario():
        pool=ClaimPool()
        await ScientificSimulationGate(pool).run_queued(limit=1)
        recovery=pool.queries[0]
        claim=pool.queries[1]
        assert "lease_expires_at<now()" in recovery
        assert "attempts>=3" in recovery
        assert "lease_token=gen_random_uuid()" in claim
        assert "attempts=target.attempts+1" in claim
    asyncio.run(scenario())


def test_scientific_trade_and_cutoff_writes_are_lease_fenced():
    import pathlib
    source=pathlib.Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "async with conn.transaction():" in source
    assert "DELETE FROM scientific_simulation_trades WHERE run_id=$1" in source
    assert "lease_token=$3 AND lease_expires_at>now()" in source
    assert "if not updated:return" in source


def test_scientific_atomic_finalization_requires_single_connection():
    import pathlib
    source=pathlib.Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert "async with self.pool.acquire() as conn:" in source
    assert "async with conn.transaction():" in source
    assert "raise RuntimeError(\"simulation lease lost during atomic finalization\")" in source
