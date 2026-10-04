import asyncio
from grid.operational_gc import cleanup_operational_state


class Pool:
    def __init__(self):self.sql=[]
    async def execute(self,sql,*args):
        self.sql.append(sql);return "DELETE 0"


def test_operational_gc_covers_terminal_research_and_compute_state():
    async def run():
        p=Pool()
        result=await cleanup_operational_state(p,30,100)
        assert set(result)=={"ml_resource_reservations","archive_compute_jobs","research_runs","ml_jobs","telegram_updates","agent_commands"}
        joined="\n".join(p.sql)
        assert "DELETE FROM research_runs" in joined
        assert "DELETE FROM archive_compute_jobs" in joined
    asyncio.run(run())
