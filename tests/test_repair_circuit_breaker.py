from grid.repair_circuit_breaker import RepairCircuitBreaker
def test_repair_circuit_breaker_opens_and_recovers_after_cooldown():
    b=RepairCircuitBreaker(max_attempts=2,window_seconds=100,cooldown_seconds=50)
    assert b.allow("n",0);b.record("n",0)
    assert b.allow("n",1);b.record("n",1)
    assert not b.allow("n",2)
    assert not b.allow("n",40)
    assert b.allow("n",60)
