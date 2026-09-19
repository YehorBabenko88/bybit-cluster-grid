from grid.control_plane_failover import QuorumPolicy
from grid.ml_experiment_factory import expand_grid

def test_last_node_keeps_telegram_but_blocks_shared_mutations():
    q=QuorumPolicy("a",peer_timeout=30)
    x=q.decide(False,[{"node_id":"a","last_seen":100}],now=100)
    assert x=={"mode":"ISOLATED_LAST_NODE","telegram":True,"mutations":False}

def test_partition_with_live_peer_does_not_create_two_emergency_leaders():
    q=QuorumPolicy("a",peer_timeout=30)
    x=q.decide(False,[{"node_id":"a","last_seen":100},{"node_id":"b","last_seen":95}],now=100)
    assert x["mode"]=="NO_LEADER" and not x["telegram"]

def test_experiment_grid_is_deterministic():
    a=list(expand_grid({"depth":[4,6],"lr":[.1,.05]}))
    b=list(expand_grid({"lr":[.1,.05],"depth":[4,6]}))
    assert a==b and len(a)==4
