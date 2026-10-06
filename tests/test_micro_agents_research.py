from grid.micro_agents import OIAgent,DeltaAgent,BookVelocityAgent,LargeOrderAgent,VolumeAgent,MicrostructureConsensus
from grid.nonlinear_research import delay_vectors,local_analog_forecast,walk_forward_analog

def _warm(agent,fn):
    for i in range(40): fn(i,1.0+(i%3)*0.001)

def test_oi_agent_learns_per_symbol_baseline_then_excites():
    a=OIAgent(z_trigger=3,refractory=2)
    oi=1000.0
    for i in range(40):
        oi*=1.00001
        a.update("BTCUSDT",i*1000,oi)
    s=a.update("BTCUSDT",41000,oi*1.10)
    assert s.state=="EXCITED" and s.score>3

def test_delta_agent_detects_instrument_relative_spike():
    a=DeltaAgent(z_trigger=3)
    for i in range(40):a.update("X",i*1000,(i%3-1)*2,100)
    s=a.update("X",41000,90,100)
    assert s.state=="EXCITED" and s.direction==1

def test_consensus_never_emits_trade_only_research_candidate():
    c=MicrostructureConsensus(max_age_ms=2000,min_agents=2)
    a=DeltaAgent(z_trigger=2);v=VolumeAgent(z_trigger=2)
    for i in range(40):
        a.update("X",i*1000,0,100);v.update("X",i*1000,100,0)
    c.update(a.update("X",41000,100,100))
    out=c.update(v.update("X",41500,10000,100))
    assert out["candidate"] is True and out["agent_count"]>=2
    assert "order" not in out and "trade" not in out

def test_delay_embedding_and_local_analogue_are_past_only_shapes():
    x=[float(i%10) for i in range(500)]
    rows=delay_vectors(x,p=4,lag=2,horizon=1)
    assert rows and len(rows[0][0])==4
    pred=local_analog_forecast(x,p=4,lag=2,horizon=1,k=10,theiler=10)
    assert pred and pred["neighbors"]==10
    wf=walk_forward_analog(x,p=3,lag=1,horizon=1,k=5,min_train=100)
    assert wf and all(r["origin_index"]+1 < len(x) for r in wf)

def test_research_schema_is_explicitly_non_trading():
    from pathlib import Path
    m=Path("grid/migrations.py").read_text(encoding="utf-8")
    assert '"micro_agent_research"' in m
    assert "research_only boolean NOT NULL DEFAULT true" in m
