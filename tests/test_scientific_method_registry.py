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
    async def fetchrow(self,q,*a):
        if q.startswith("SELECT schema_version"):return None
        return None
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


def test_schema_upgrade_requires_explicit_compatibility():
    class ExistingPool(FakePool):
        async def fetchrow(self,q,*a):
            if q.startswith("SELECT schema_version"):return {"schema_version":1}
            return None
    async def scenario():
        pool=ExistingPool();r=ScientificMethodRegistry()
        r.register(ScientificMethod("m","2",2,lambda e:{},{}))
        try:
            await r.sync_db(pool)
            assert False,"schema upgrade should fail closed"
        except RuntimeError:
            pass
        ok=ScientificMethodRegistry()
        ok.register(ScientificMethod("m","2",2,lambda e:{},{},compatible_from=(1,)))
        await ok.sync_db(pool)
    asyncio.run(scenario())


def test_nonfinite_scientific_observation_is_quarantined_without_stopping_other_methods():
    async def scenario():
        pool=FakePool();registry=ScientificMethodRegistry(quarantine_after=1)
        registry.register(ScientificMethod("nan_method","1",1,lambda event:{"score":float("nan")},{}))
        registry.register(ScientificMethod("healthy","1",1,lambda event:{"score":0.25},{}))
        await registry.sync_db(pool)
        result=await registry.dispatch(pool,{"event_type":"observation"})
        assert result["nan_method"]["ok"] is False
        assert pool.status["nan_method"]=="QUARANTINED"
        assert result["healthy"]["ok"] is True
    asyncio.run(scenario())


def test_scientific_method_registration_rejects_invalid_handler_and_capabilities():
    registry=ScientificMethodRegistry()
    for method in (
        ScientificMethod("invalid","1",1,None,{}),
        ScientificMethod("bad_json","1",1,lambda event:{},{"x":float("inf")}),
        ScientificMethod("","1",1,lambda event:{},{}),
    ):
        try:
            registry.register(method)
        except (ValueError,TypeError):
            pass
        else:
            raise AssertionError("invalid method registration was accepted")
