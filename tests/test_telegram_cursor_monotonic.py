import asyncio
from grid.control_replication import commit_telegram_cursor

class FakePool:
    def __init__(self):self.cursor=0;self.calls=0
    async def fetchrow(self,sql,*args):
        self.calls+=1
        assert "ON CONFLICT" in sql and "WHERE COALESCE" in sql
        value=args[0]
        if value>self.cursor:
            self.cursor=value
            return {"next_update_id":value}
        return None

def test_cursor_advance_is_single_atomic_upsert():
    async def scenario():
        p=FakePool()
        assert await commit_telegram_cursor(p,"leader-a",12)==12
        assert p.calls==1
    asyncio.run(scenario())

def test_negative_cursor_rejected_before_db_write():
    async def scenario():
        p=FakePool()
        try:
            await commit_telegram_cursor(p,"leader-a",-1)
        except ValueError:
            pass
        else:
            raise AssertionError("negative cursor accepted")
        assert p.calls==0
    asyncio.run(scenario())
