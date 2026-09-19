from grid.ml_resource_scheduler import Workload,choose_node
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
