import time
from grid.distributed_acceptance import distributed_acceptance_status


def node(*,strat=True,archive=True,version="v1",age=0,cpu=10,ram=20,disk=100):
    return {"last_seen":time.time()-age,"cpu_pct":cpu,"ram_pct":ram,"disk_free":disk*1024**3,
            "operator_stopped":False,"bootstrap_paused":False,
            "compute_capabilities":{"strattester":strat,"archive":archive},
            "strattester_version":version}


def test_acceptance_ready_with_two_consistent_healthy_nodes():
    out=distributed_acceptance_status({"a":node(),"b":node()},
        heartbeat_seconds=10,cpu_limit=75,ram_limit=78,disk_free_gb=25)
    assert out["ready"] is True
    assert out["strattester_nodes"]==["a","b"]


def test_acceptance_blocks_version_mismatch_and_pressure():
    out=distributed_acceptance_status({
        "a":node(version="v1"),
        "b":node(version="v2"),
        "hot":node(cpu=99),
    },heartbeat_seconds=10,cpu_limit=75,ram_limit=78,disk_free_gb=25)
    assert out["ready"] is False
    assert any("versions differ" in x for x in out["reasons"])
    assert "hot" not in out["eligible"]
