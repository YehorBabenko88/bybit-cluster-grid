import copy,pytest
from s0_smoke.wire import ServerState,validate_summary,validate_reply
from s0_smoke.protocol import MarketState
CTX=dict(head='a'*40,run_id='11111111-1111-4111-8111-111111111111')
def msg(seq=1,op='register',stats=None):return dict(schema=1,**CTX,node='PC4',seq=seq,op=op,stats=stats)
def test_register_heartbeat_and_duplicate():
 s=ServerState(CTX);v=msg();r=s.accept(v,1000);assert r['assignment']==['orderbook.1.BTCUSDT','publicTrade.BTCUSDT'];assert s.accept(v,900)==r
 st=MarketState().summary();s.accept(msg(2,'heartbeat',st),900);assert s.heartbeats==1
 with pytest.raises(ValueError):s.accept(msg(2,'final',st),800)
@pytest.mark.parametrize('field,value',[('schema',True),('head','b'*40),('node','LS5'),('seq',True),('seq',0),('seq',2),('op','trade'),('op','private'),('stats',{}),('api_key','key')])
def test_wrong_registration(field,value):
 v=msg();v[field]=value
 with pytest.raises(ValueError):ServerState(CTX).accept(v,1000)
def test_no_counter_regression_or_gap():
 s=ServerState(CTX);s.accept(msg(),1000);st=MarketState().summary();st.update(trade_count=2,buy_count=1,sell_count=1,buy_volume='1',sell_volume='1');s.accept(msg(2,'heartbeat',st),800)
 with pytest.raises(ValueError):s.accept(msg(3,'heartbeat',MarketState().summary()),500)
 with pytest.raises(ValueError):s.accept(msg(4,'heartbeat',st),500)
@pytest.mark.parametrize('field,value',[('trade_count',True),('buy_volume','NaN'),('sell_volume','1e9'),('trade_count',-1),('connections',0),('api_key','x'),('last_trade_ts',True)])
def test_unsafe_summary(field,value):
 v=MarketState().summary();v[field]=value
 with pytest.raises(ValueError):validate_summary(v)
def test_changed_or_stale_reply():
 v=ServerState(CTX).accept(msg(),1000);validate_reply(v,CTX,1)
 for field,val in [('head','b'*40),('seq',True),('stop','false'),('remaining_ms',300001),('assignment',['order.create'])]:
  w=copy.deepcopy(v);w[field]=val
  with pytest.raises(ValueError):validate_reply(w,CTX,1)
