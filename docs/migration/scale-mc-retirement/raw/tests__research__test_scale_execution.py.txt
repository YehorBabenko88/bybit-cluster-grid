from strattester.research.execution import ExecutionPolicy,ScaleSignal,simulate_scale_trade

def b(t,o,h,l,c): return {'t':t,'open':o,'high':h,'low':l,'close':c}

def test_scale_trade_has_two_independent_entry_legs_and_partial_targets():
    bars=[
      b(0,100,101,99,100),
      b(60,99,100,98,99),
      b(120,98,99,97,98),
      b(180,101,102,98,101),
      b(240,103,104,100,103),
    ]
    s=ScaleSignal(decision_time=0,side='long',entries=((99,.5),(98,.5)),stop_loss=95,take_profits=((101,.5),(103,.5)))
    t=simulate_scale_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0,position_usd=100))
    assert len(t.fills)==2
    assert [x.reason for x in t.exits]==['TP1','TP2']
    assert abs(sum(x.quantity for x in t.exits)-sum(x.quantity for x in t.fills))<1e-12

def test_scale_trade_does_not_share_state_between_calls():
    bars=[b(0,100,101,99,100),b(60,99,100,98,99),b(120,101,102,98,101)]
    s=ScaleSignal(decision_time=0,side='long',entries=((99,1.0),),stop_loss=95,take_profits=((101,1.0),))
    a=simulate_scale_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    z=simulate_scale_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0))
    assert a==z

def b(t,o,h,l,c): return {'t':t,'open':o,'high':h,'low':l,'close':c}

def test_scale_trade_can_move_stop_after_first_target():
    bars=[
      b(0,100,100,99,100),
      b(60,99,100,98,99),
      b(120,101,102,100,101),
      b(180,99,100,98,99),
    ]
    s=ScaleSignal(decision_time=0,side='long',entries=((99,1.0),),stop_loss=95,
                  take_profits=((101,.5),(103,.5)),move_stop_to_entry_after_tp1=True)
    t=simulate_scale_trade(s,bars,ExecutionPolicy(bar_ms=60,fee_rate=0,position_usd=100))
    assert [x.reason for x in t.exits]==['TP1','SL']
    assert t.exits[-1].price==99
