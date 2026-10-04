import asyncio
from grid.operational_gc import cleanup_operational_state


class BoundedPool:
    def __init__(self):
        self.calls=0
    async def execute(self,sql,*args):
        self.calls+=1
        # Simulate a database that always has at least one old row available.
        # The contract is one bounded DELETE statement per table per maintenance pass.
        return "DELETE 1"


def test_operational_gc_work_per_pass_is_bounded():
    async def run():
        p=BoundedPool()
        for _ in range(25):
            result=await cleanup_operational_state(p,30,100)
            assert set(result)=={"ml_resource_reservations","archive_compute_jobs","research_runs","ml_jobs"}
        assert p.calls==25*4
    asyncio.run(run())
