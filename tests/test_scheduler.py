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
