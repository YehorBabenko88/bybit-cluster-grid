from grid.pressure import *

def snap(cpu=10,ram=20,disk=100):
    return {"cpu_pct":cpu,"ram_pct":ram,"disk_free":disk*1024**3}

def test_pressure_requires_sustained_bad_ticks():
    p=PressureController()
    assert p.update(snap(cpu=80))==NORMAL
    assert p.update(snap(cpu=80))==SOFT_PRESSURE
    for _ in range(4): p.update(snap(cpu=80))
    assert p.state==REDUCE_LOAD

def test_critical_enters_quickly_and_recovery_has_hysteresis():
    p=PressureController()
    p.update(snap(cpu=99)); p.update(snap(cpu=99))
    assert p.state==CRITICAL
    for _ in range(5): p.update(snap())
    assert p.state!=NORMAL
    p.update(snap())
    assert p.state==NORMAL

def test_heaviest_symbols_are_drained_first():
    p=PressureController(state=REDUCE_LOAD)
    for _ in range(5):
        p.observe_symbol("BTCUSDT",1000,100)
        p.observe_symbol("ETHUSDT",500,50)
        p.observe_symbol("QUIETUSDT",2,1)
        p.observe_symbol("MIDUSDT",100,10)
    drained=p.symbols_to_drain(["BTCUSDT","ETHUSDT","QUIETUSDT","MIDUSDT"])
    assert drained==["BTCUSDT"]

def test_soft_pressure_does_not_shed():
    p=PressureController(state=SOFT_PRESSURE)
    assert p.symbols_to_drain(["BTCUSDT"])==[]
