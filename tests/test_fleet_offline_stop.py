import asyncio,json
from grid import fleet_control as fc


class Pool:
    def __init__(self,action="STOP"):
        self.action=action;self.states=[];self.execs=[]
    async def fetchrow(self,sql,*args):
        if "FROM fleet_operations" in sql:
            return {"id":"op","action":self.action,"status":"RUNNING",
                    "snapshot":json.dumps({}),"targets":json.dumps(["offline-node"])}
        return None
    async def fetch(self,sql,*args):
        if "FROM agent_commands" in sql:return []
        return []
    async def execute(self,sql,*args):
        self.execs.append((sql,args));return "UPDATE 1"


def test_stop_closes_global_gate_even_before_offline_node_ack(monkeypatch):
    async def run():
        p=Pool("STOP")
        async def state(pool,state,requested_by,reason=None):
            p.states.append(state);return {"state":state}
        monkeypatch.setattr(fc,"set_runtime_state",state)
        out=await fc.reconcile_fleet_operation(p)
        assert out["status"]=="RUNNING"
        assert out["pending"]==["offline-node"]
        assert p.states==["STOPPED"]
    asyncio.run(run())


def test_resume_never_opens_gate_before_all_node_acks(monkeypatch):
    async def run():
        p=Pool("RESUME")
        async def state(pool,state,requested_by,reason=None):
            p.states.append(state);return {"state":state}
        monkeypatch.setattr(fc,"set_runtime_state",state)
        out=await fc.reconcile_fleet_operation(p)
        assert out["status"]=="RUNNING"
        assert p.states==[]
    asyncio.run(run())
