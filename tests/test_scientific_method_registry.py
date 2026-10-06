import asyncio
from grid.scientific_method_registry import ScientificMethod,ScientificMethodRegistry

class FakePool:
    def __init__(self):self.status={};self.failures={}
    async def execute(self,q,*a):
        if "INSERT INTO scientific_methods" in q:self.status.setdefault(a[0],"ENABLED");return "OK"
        if "UPDATE scientific_methods SET failure_count=0" in q:self.failures[a[0]]=0;return "OK"
        if "INSERT INTO scientific_method_errors" in q:return "OK"
        if "INSERT INTO scientific_method_events" in q:return "OK"
        return "OK"
    async def fetchval(self,q,*a):
        if q.startswith("SELECT status"):return self.status.get(a[0],"ENABLED")
        if "RETURNING failure_count" in q:
            k=a[0];self.failures[k]=self.failures.get(k,0)+1
            if self.failures[k]>=a[2]:self.status[k]="QUARANTINED"
            return self.failures[k]
        return None

def test_broken_scientific_method_does_not_break_healthy_method():
    async def scenario():
        pool=FakePool();r=ScientificMethodRegistry(quarantine_after=2)
        r.register(ScientificMethod("bad","1",1,lambda e:1/0,{}))
        r.register(ScientificMethod("good","1",1,lambda e:{"x":e["x"]+1},{}))
        await r.sync_db(pool)
        first=await r.dispatch(pool,{"event_type":"x","x":2})
        assert not first["bad"]["ok"] and first["good"]["payload"]["x"]==3
        await r.dispatch(pool,{"event_type":"x","x":2})
        assert pool.status["bad"]=="QUARANTINED"
        third=await r.dispatch(pool,{"event_type":"x","x":2})
        assert "bad" not in third and third["good"]["ok"]
    asyncio.run(scenario())

def test_scientific_plugin_migration_uses_jsonb_extension_payloads():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert 'scientific_method_plugins' in m
    assert "payload jsonb" in m and "config jsonb" in m and "capabilities jsonb" in m
