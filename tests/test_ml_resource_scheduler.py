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
