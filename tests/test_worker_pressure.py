"""Exercise pressure through real heartbeat cycles, including CONTROL outages."""
import asyncio

import pytest

from grid.worker import Worker
from grid import worker as module


async def heartbeat_cycles(monkeypatch, tmp_path, ticks):
    monkeypatch.chdir(tmp_path)
    worker=Worker()
    worker.meta={symbol:{"tick_size":1} for symbol in "ABCD"}
    metrics={"queue_ratio":0,"queue_depth":0,"queue_capacity":1,
             "writes_per_sec":0,"write_failures":0,"avg_write_latency_ms":0}
    index=0
    observed=[]
    async def reconcile():
        pass
    worker.reconcile=reconcile
    monkeypatch.setattr(worker.storage,"metrics",lambda:dict(metrics,replay_active=ticks[index].get("replay",False)))
    monkeypatch.setattr(worker.micro_storage,"metrics",lambda:dict(metrics))
    monkeypatch.setattr(module,"snapshot",lambda:{"node_id":"test","cpu_pct":ticks[index].get("cpu",10),"ram_pct":20,"disk_free":100*1024**3})
    monkeypatch.setattr(module,"internet_available",lambda:True)
    monkeypatch.setattr(module,"mark_internet_success",lambda:None)
    monkeypatch.setattr(module,"mark_coordinator_success",lambda:None)
    class Reply:
        status=200
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def json(self):
            return dict(runtime_state="ACTIVE",market_work_enabled=True,
                        symbols=ticks[index].get("symbols",list("ABCD")),
                        micro_symbols=ticks[index].get("micro",list("ABCD")),
                        commands=ticks[index].get("commands",[]),
                        recovery_profile=ticks[index].get("recovery_profile",{}))
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def post(self,*args,**kwargs):
            if ticks[index].get("offline",False): raise OSError("CONTROL offline")
            return Reply()
    monkeypatch.setattr(module.aiohttp,"ClientSession",Session)
    async def sleep(_):
        nonlocal index
        if "recovery_profile" in ticks[index]:
            profile=ticks[index]["recovery_profile"]
            assert worker.db is None
            assert worker.storage.replay_rate==profile["minute_per_second"]
            assert worker.micro_storage.replay_rate==profile["micro_per_second"]
        observed.append((set(worker.wanted),set(worker.micro_wanted),set(worker.pressure_drained)))
        index+=1
        if index==len(ticks): raise asyncio.CancelledError
    monkeypatch.setattr(module.asyncio,"sleep",sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.heartbeat()
    return observed


@pytest.mark.parametrize("offline",[True,False])
def test_sustained_pressure_has_bounded_drain(monkeypatch,tmp_path,offline):
    ticks=[{}]+[{"cpu":80,"offline":offline} for _ in range(16)]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[-1]==(set("ABC"),set("ABC"),{"D"})


def test_fully_drained_offline_assignment_and_micro_recover(monkeypatch,tmp_path):
    ticks=[{"symbols":["D"],"micro":["D"]}]
    ticks += [{"cpu":99,"offline":True} for _ in range(4)]
    ticks += [{"offline":True} for _ in range(12)]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[4]==(set(),set(),{"D"})
    assert observed[-1]==({"D"},{"D"},set())


def test_reassignment_forgets_old_drained_symbols(monkeypatch,tmp_path):
    ticks=[{}]+[{"cpu":99} for _ in range(4)]
    ticks += [{"cpu":99,"symbols":["X","Y"],"micro":["X","Y"]}]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[-1]==({"X"},{"X"},{"Y"})


def test_offline_wal_replay_suppresses_micro_then_restores(monkeypatch,tmp_path):
    ticks=[{}, {"offline":True,"replay":True}, {"offline":True}]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[1][1]==set()
    assert observed[2][1]==set("ABCD")


@pytest.mark.parametrize("action",["stop","pause"])
def test_pressure_recovery_respects_stop_and_pause(monkeypatch,tmp_path,action):
    monkeypatch.setenv("ProgramData",str(tmp_path))
    # Commands are already authorized by CONTROL; recovery must not recreate load.
    ticks=[{}]+[{"cpu":99} for _ in range(2)]
    ticks += [{"cpu":99,"commands":[{"id":"test","action":action}]}]
    ticks += [{"offline":True} for _ in range(12)]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[-1][0]==set()
    assert observed[-1][1]==set()


def test_critical_escalation_and_recovery_keep_micro_subset(monkeypatch,tmp_path):
    ticks=[{"micro":["A","D"]}]
    ticks += [{"cpu":80,"offline":True} for _ in range(6)]
    ticks += [{"cpu":99,"offline":True} for _ in range(2)]
    ticks += [{"offline":True} for _ in range(12)]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[6]==(set("ABC"),{"A"},{"D"})
    assert observed[8]==(set("AB"),{"A"},set("CD"))
    assert observed[-1]==(set("ABCD"),set("AD"),set())


def test_db_less_worker_applies_control_replay_rates(monkeypatch,tmp_path):
    ticks=[{"recovery_profile":{"minute_per_second":3,"micro_per_second":7}}]
    observed=asyncio.run(heartbeat_cycles(monkeypatch,tmp_path,ticks))
    assert observed[0][0]==set("ABCD")

@pytest.mark.parametrize('sink_name',['storage','micro_storage'])
def test_failed_wal_exits_heartbeat_without_control(monkeypatch,tmp_path,sink_name):
    from grid import worker as module
    monkeypatch.setenv('ProgramData',str(tmp_path))
    worker=module.Worker()
    monkeypatch.setattr(module,'snapshot',lambda:{})
    monkeypatch.setattr(module,'replica_meta',lambda _:{})
    for name in ('storage','micro_storage'):
        sink=getattr(worker,name)
        metrics=sink.metrics()
        monkeypatch.setattr(sink,'metrics',lambda name=name,metrics=metrics:{**metrics,'replay_failed':name==sink_name})
    class Session:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def post(self,*args,**kwargs):raise AssertionError('must restart without CONTROL')
    monkeypatch.setattr(module.aiohttp,'ClientSession',Session)
    with pytest.raises(RuntimeError,match="WAL recovery requires worker restart"):
        asyncio.run(asyncio.wait_for(worker.heartbeat(),timeout=1))
    assert worker.restart_requested
