from grid.ml_resource_scheduler import Workload,choose_node,rank_nodes
from grid.ml_adaptive_load import AdaptiveConcurrency

def node(cpu,ram_gb,disk_gb,cores=8,loc=None,lan=1000):
    return {"cpu_pct":cpu,"ram_available":ram_gb*1024**3,"disk_free":disk_gb*1024**3,
            "cpu_count":cores,"pressure_state":"NORMAL","data_location":loc,"lan_mbps":lan}
def test_scheduler_prefers_local_data_when_transfer_is_expensive():
    nodes={"local":node(40,16,100,8,"db",1000),"remote":node(10,32,100,16,None,100)}
    pick=choose_node(nodes,Workload("dataset",ram_gb=4,scratch_gb=5,input_gb=100,data_locality="db"))
    assert pick[1]=="local"
def test_adaptive_concurrency_sheds_load_fast_and_adds_slowly():
    c=AdaptiveConcurrency(max_workers=4); c.current=3
    assert c.update(90,60,30,.1,100)==2
    for _ in range(5): c.update(20,30,20,.1,100)
    assert c.current==2
    assert c.update(20,30,20,.1,100)==3


def test_disk_pressure_nodes_are_not_ranked():
    nodes={"ok":{"pressure_state":"NORMAL","disk_pressure_state":"NORMAL","cpu_pct":10,
                 "ram_available":16*1024**3,"disk_free":100*1024**3,"cpu_count":8},
           "soft":{"pressure_state":"NORMAL","disk_pressure_state":"SOFT","cpu_pct":1,
                   "ram_available":64*1024**3,"disk_free":100*1024**3,"cpu_count":32}}
    ranked=rank_nodes(nodes,Workload("train",cpu=4,ram_gb=8,scratch_gb=10))
    assert [x[1] for x in ranked]==["ok"]


def test_scheduler_rejects_negative_and_nonfinite_requests():
    nodes={"node":node(10,32,100)}
    for kwargs in ({"ram_gb":-1},{"scratch_gb":-2},{"cpu":-1},
                   {"ram_gb":float("nan")},{"cpu":float("inf")},
                   {"input_gb":float("-inf")}):
        assert choose_node(nodes,Workload("train",**kwargs)) is None


def test_dispatcher_accounts_for_reservations_within_same_batch():
    from pathlib import Path
    source=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    assert 'selected=nodes[node_id]' in source
    assert 'selected["ram_available"]=max(0.0' in source
    assert 'selected["disk_free"]=max(0.0' in source
    assert 'selected["cpu_pct"]=min(100.0' in source


def test_scheduler_enforces_requested_cpu_capacity():
    nodes={"busy":node(70,64,100,cores=8)}
    assert choose_node(nodes,Workload("train",cpu=4,ram_gb=8,scratch_gb=10)) is None
    assert choose_node(nodes,Workload("train",cpu=1,ram_gb=8,scratch_gb=10)) is not None


def test_scheduler_rejects_corrupted_node_telemetry():
    for field,value in (("cpu_pct",float("nan")),
                        ("cpu_pct",-1),("ram_available",float("inf")),
                        ("disk_free",-1),("cpu_count",0),
                        ("lan_mbps",float("nan")),("lan_mbps",0)):
        bad=node(10,32,100)
        bad[field]=value
        assert choose_node({"bad":bad},Workload("train",cpu=2,ram_gb=4,scratch_gb=5)) is None


def test_dispatch_uses_transaction_scoped_postgres_lock():
    from pathlib import Path
    source=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock($1)" in source
    transaction=source.index("async with c.transaction():")
    lock=source.index("pg_advisory_xact_lock($1)")
    reservations=source.index("reservations=await reserved_by_node(c)")
    active=source.index("active=await c.fetchval(")
    assignment=source.index("UPDATE ml_jobs SET status='assigned'")
    assert transaction<lock<reservations<active<assignment
    assert "reservations=await reserved_by_node(self.pool)" not in source


def test_dispatch_reservation_adjustment_keeps_node_telemetry_immutable():
    from grid.ml_dispatcher import _adjust_nodes
    original={"n":{"ram_available":16*1024**3,"disk_free":40*1024**3,
                   "cpu_pct":10,"cpu_count":8,"gpu_available":True}}
    adjusted=_adjust_nodes(original,{"n":{"ram_gb":4,"scratch_gb":5,"cpu":2}})
    assert adjusted["n"]["ram_available"]==12*1024**3
    assert adjusted["n"]["disk_free"]==35*1024**3
    assert adjusted["n"]["cpu_pct"]==35
    assert original["n"]["ram_available"]==16*1024**3


def test_existing_gpu_reservation_blocks_second_gpu_job():
    from grid.ml_dispatcher import _adjust_nodes
    reported={"gpu-node":{**node(10,32,100),"gpu_available":True}}
    adjusted=_adjust_nodes(reported,{"gpu-node":{"cpu":1,"ram_gb":1,"scratch_gb":1,"gpu":True}})
    assert adjusted["gpu-node"]["gpu_available"] is False
    assert choose_node(adjusted,Workload("train",gpu=True,ram_gb=4,scratch_gb=5)) is None


def test_dispatch_collects_telemetry_before_lock_and_reads_reservations_after():
    from pathlib import Path
    source=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    lock=source.index("pg_advisory_xact_lock($1)")
    telemetry=source.index("reported=await asyncio.wait_for(self.node_provider(),timeout=10)")
    reservations=source.index("reservations=await reserved_by_node(c)")
    assert telemetry<lock<reservations


def test_dispatch_payload_decodes_asyncpg_jsonb_text():
    import pytest
    from grid.ml_dispatcher import _job_payload
    assert _job_payload('{"cpu":4,"ram_gb":4}')=={"cpu":4,"ram_gb":4}
    assert _job_payload({"cpu":2})=={"cpu":2}
    assert _job_payload(None)=={}
    for invalid in ('[]','null','"text"','{invalid',[]):
        with pytest.raises((ValueError,TypeError)):
            _job_payload(invalid)


def test_dispatch_uses_wall_clock_after_waiting_for_postgres_lock():
    from pathlib import Path
    dispatcher=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    reservations=Path("grid/ml_reservations.py").read_text(encoding="utf-8")
    assert "lease_until>=clock_timestamp()" in dispatcher
    assert "not_before<=clock_timestamp()" in dispatcher
    assert "expires_at>=clock_timestamp()" in reservations


def test_ml_lease_lifecycle_reservation_fencing_contract():
    from pathlib import Path
    concurrency=Path("grid/ml_concurrency.py").read_text(encoding="utf-8")
    recovery=Path("grid/ml_orchestrator_service.py").read_text(encoding="utf-8")
    renew=concurrency.split("async def renew_ml_job(",1)[1].split("async def finish_ml_job(",1)[0]
    finish=concurrency.split("async def finish_ml_job(",1)[1].split("async def acquire_service_lease(",1)[0]
    assert "async with c.transaction():" in renew
    assert "lease_generation=$4" in renew
    assert "UPDATE ml_resource_reservations SET" in renew
    assert "async with c.transaction():" in finish
    assert "lease_generation=$5" in finish
    assert "DELETE FROM ml_resource_reservations" in finish
    assert "NOT EXISTS (" in recovery
    assert "j.status IN ('assigned','running')" in recovery

def test_dispatch_telemetry_timeout_never_opens_database_transaction():
    import asyncio
    import pytest
    from grid.ml_dispatcher import MLDispatcher

    class PoolMustNotBeUsed:
        def acquire(self):
            raise AssertionError("database connection acquired before telemetry completed")

    async def never_returns():
        await asyncio.Event().wait()

    async def scenario():
        dispatcher=MLDispatcher(PoolMustNotBeUsed(),never_returns)
        # Replace the 10-second wait with a short real timeout while preserving
        # cancellation semantics of the async telemetry coroutine.
        original=asyncio.wait_for
        async def short_wait(awaitable,timeout):
            assert timeout==10
            return await original(awaitable,timeout=0.02)
        from unittest.mock import patch
        with patch("grid.ml_dispatcher.asyncio.wait_for",short_wait):
            with pytest.raises(asyncio.TimeoutError):
                await dispatcher(1)
    asyncio.run(scenario())
