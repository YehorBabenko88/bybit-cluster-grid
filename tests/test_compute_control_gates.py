from grid import coordinator as c


def test_node_compute_gate_respects_telegram_stop_and_pause():
    old=dict(c.nodes)
    try:
        c.nodes.clear()
        c.nodes["running"]={"operator_stopped":False,"bootstrap_paused":False}
        c.nodes["stopped"]={"operator_stopped":True,"bootstrap_paused":False}
        c.nodes["paused"]={"operator_stopped":False,"bootstrap_paused":True}
        assert c._node_compute_block_reason("running") is None
        assert "operator-stopped" in c._node_compute_block_reason("stopped")
        assert "paused" in c._node_compute_block_reason("paused")
    finally:
        c.nodes.clear();c.nodes.update(old)
