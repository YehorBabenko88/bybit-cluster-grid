from grid.resources import normalized_node_role,node_accepts_work,node_accepts_control

def test_dev_observer_capabilities_are_fail_closed():
    snap={"node_role":"DEV_OBSERVER"}
    assert normalized_node_role(snap["node_role"])=="DEV_OBSERVER"
    assert node_accepts_work(snap) is False
    assert node_accepts_control(snap) is False

def test_worker_accepts_work_but_not_control():
    snap={"node_role":"WORKER"}
    assert node_accepts_work(snap) is True
    assert node_accepts_control(snap) is False

def test_control_is_explicitly_control_capable():
    snap={"node_role":"CONTROL"}
    assert node_accepts_work(snap) is True
    assert node_accepts_control(snap) is True

def test_unknown_role_falls_back_to_worker_for_legacy_compatibility():
    assert normalized_node_role("old-value")=="WORKER"
