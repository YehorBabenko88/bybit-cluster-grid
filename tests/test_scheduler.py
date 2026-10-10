from grid.scheduler import learned_symbol_cost,weighted_assign

def test_cost_uses_cross_node_median():
    nodes={
      "A":{"symbol_cost":{"BTC":100,"ETH":20}},
      "B":{"symbol_cost":{"BTC":120,"ETH":22}},
      "C":{"symbol_cost":{"BTC":10000}},
    }
    costs,fallback=learned_symbol_cost(nodes)
    assert costs["BTC"]==120
    assert costs["ETH"]==21
    assert fallback>=1

def test_heavy_symbols_do_not_cluster_when_capacity_equal():
    nodes={"A":{"symbol_cost":{"BTC":100,"ETH":90,"X":1,"Y":1}},
           "B":{"symbol_cost":{"BTC":100,"ETH":90,"X":1,"Y":1}}}
    out=weighted_assign(["BTC","ETH","X","Y"],{"A":1,"B":1},nodes)
    assert ("BTC" in out["A"]) != ("ETH" in out["A"])

def test_stronger_node_accepts_more_weight():
    nodes={"A":{"symbol_cost":{"BTC":100,"ETH":50,"X":10,"Y":10}},
           "B":{"symbol_cost":{"BTC":100,"ETH":50,"X":10,"Y":10}}}
    out=weighted_assign(["BTC","ETH","X","Y"],{"A":3,"B":1},nodes)
    costs={"BTC":100,"ETH":50,"X":10,"Y":10}
    la=sum(costs[s] for s in out["A"]); lb=sum(costs[s] for s in out["B"])
    assert la>=lb

def test_unknown_symbol_has_nonzero_fallback():
    nodes={"A":{"symbol_cost":{"BTC":50}},"B":{"symbol_cost":{"BTC":50}}}
    costs,fallback=learned_symbol_cost(nodes)
    assert fallback>0
    out=weighted_assign(["BTC","NEW"],{"A":1,"B":1},nodes)
    assert sorted(out["A"]+out["B"])==["BTC","NEW"]

def test_drained_symbol_moves_off_reduce_load_node():
    nodes={
      "A":{"pressure_state":"REDUCE_LOAD","drained_symbols":["BTC"],"symbol_cost":{"BTC":100}},
      "B":{"pressure_state":"NORMAL","symbol_cost":{"BTC":100}},
    }
    out=weighted_assign(["BTC"],{"A":10,"B":1},nodes)
    assert out["A"]==[]
    assert out["B"]==["BTC"]

def test_critical_node_is_avoided_for_all_symbols():
    nodes={"A":{"pressure_state":"CRITICAL"},"B":{"pressure_state":"NORMAL"}}
    out=weighted_assign(["BTC","ETH"],{"A":100,"B":1},nodes)
    assert out["A"]==[]
    assert sorted(out["B"])==["BTC","ETH"]

def test_recovered_node_can_receive_symbol_again():
    nodes={"A":{"pressure_state":"NORMAL","drained_symbols":[]},"B":{"pressure_state":"NORMAL"}}
    out=weighted_assign(["BTC"],{"A":10,"B":1},nodes)
    assert out["A"]==["BTC"]

def test_all_critical_nodes_pause_collection():
    nodes={"A":{"pressure_state":"CRITICAL"},"B":{"pressure_state":"CRITICAL"}}
    out=weighted_assign(["BTCUSDT"],{"A":1,"B":1},nodes)
    assert out=={"A":[],"B":[]}


def test_dev_observer_never_receives_market_work():
    nodes={
      "HOME":{"accepts_work":False,"node_role":"DEV_OBSERVER","pressure_state":"NORMAL"},
      "WORK":{"accepts_work":True,"node_role":"WORKER","pressure_state":"NORMAL"},
    }
    out=weighted_assign(["BTC","ETH"],{"HOME":1000,"WORK":1},nodes)
    assert "HOME" not in out
    assert sorted(out["WORK"])==["BTC","ETH"]

def test_observer_can_be_enabled_later_by_role_change():
    nodes={
      "HOME":{"accepts_work":True,"node_role":"WORKER","pressure_state":"NORMAL"},
      "WORK":{"accepts_work":True,"node_role":"WORKER","pressure_state":"NORMAL"},
    }
    out=weighted_assign(["BTC"],{"HOME":1000,"WORK":1},nodes)
    assert out["HOME"]==["BTC"]


def test_observer_disappearance_does_not_change_worker_assignment():
    symbols=["BTC","ETH","SOL"]
    workers={"W1":{"accepts_work":True,"pressure_state":"NORMAL"},
             "W2":{"accepts_work":True,"pressure_state":"NORMAL"}}
    with_home={**workers,"HOME":{"accepts_work":False,"node_role":"DEV_OBSERVER","pressure_state":"NORMAL"}}
    scores_with={"W1":2,"W2":1,"HOME":999}
    scores_without={"W1":2,"W2":1}
    a=weighted_assign(symbols,scores_with,with_home)
    b=weighted_assign(symbols,scores_without,workers)
    assert a==b


def test_invalid_symbol_costs_are_ignored():
    import math
    costs, fallback=learned_symbol_cost({
        "A":{"symbol_cost":{"BTCUSDT":float("inf"),"ETHUSDT":float("nan"),"SOLUSDT":-3}},
        "B":{"symbol_cost":{"BTCUSDT":7}},
    })
    assert costs=={"BTCUSDT":7}
    assert math.isfinite(fallback)
    out=weighted_assign(["BTCUSDT","ETHUSDT"],{"A":1,"B":1},{
        "A":{"symbol_cost":{"BTCUSDT":float("inf")}},
        "B":{"symbol_cost":{"BTCUSDT":7}},
    })
    assert sorted(out["A"]+out["B"])==["BTCUSDT","ETHUSDT"]


def test_zero_negative_nonfinite_capacity_never_gets_work():
    nodes={key:{"pressure_state":"NORMAL"} for key in ("zero","negative","nan","inf","valid")}
    out=weighted_assign(["BTCUSDT"],{
        "zero":0,"negative":-1,"nan":float("nan"),"inf":float("inf"),"valid":2},nodes)
    assert out=={"valid":["BTCUSDT"]}


def test_all_invalid_capacities_result_in_no_assignment():
    assert weighted_assign(["BTCUSDT"],{"A":0,"B":float("nan")},{})=={}


def test_stabilization_zero_churn_keeps_healthy_owner():
    from grid.scheduler import stabilize_assignments
    proposed={"A":[],"B":["BTCUSDT"]}
    current={"A":["BTCUSDT"],"B":[]}
    nodes={"A":{"pressure_state":"NORMAL"},"B":{"pressure_state":"NORMAL"}}
    assert stabilize_assignments(proposed,current,nodes,0)==current


def test_stabilization_invalid_churn_is_conservative():
    from grid.scheduler import stabilize_assignments
    proposed={"A":[],"B":["BTCUSDT"]}
    current={"A":["BTCUSDT"],"B":[]}
    nodes={"A":{"pressure_state":"NORMAL"},"B":{"pressure_state":"NORMAL"}}
    assert stabilize_assignments(proposed,current,nodes,float("nan"))==current
