from grid.ml_resource_scheduler import Workload,choose_node
def test_reserved_capacity_can_make_busy_node_ineligible():
    nodes={"a":{"cpu_pct":10,"cpu_count":8,"ram_available":16*1024**3,"disk_free":100*1024**3,"pressure_state":"NORMAL"}}
    assert choose_node(nodes,Workload("train",ram_gb=8,scratch_gb=5))
    nodes["a"]["ram_available"]=7*1024**3
    assert choose_node(nodes,Workload("train",ram_gb=8,scratch_gb=5)) is None
