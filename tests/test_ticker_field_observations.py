"""Synthetic socket frames only; no exchange, database or trading qualification."""
import asyncio,hashlib,json
import pytest
from grid import microstructure as module

class Socket:
 def __init__(self,frames):self.frames=iter(frames)
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 async def send(self,*args):pass
 async def recv(self):
  try:return next(self.frames)
  except StopIteration:raise asyncio.CancelledError
class DB:
 def __init__(self):self.rows=[]
 async def insert_event(self,symbol,ts,kind,payload):self.rows.append((symbol,ts,kind,payload))
def frame(ts,data):
 out={'topic':'tickers.BTCUSDT','data':data}
 if ts is not None:out['ts']=ts
 return json.dumps(out)
def run(monkeypatch,frames):
 async def scenario():
  async def ready():pass
  socket=Socket([json.dumps({'op':'subscribe','success':True}),*frames]);db=DB()
  monkeypatch.setattr(module,'wait_for_internet',ready)
  monkeypatch.setattr(module.websockets,'connect',lambda *a,**kw:socket)
  monkeypatch.setattr(module.time,'time',lambda:2000.)
  with pytest.raises(asyncio.CancelledError):await module.MicrostructureCollector(db,snapshot_ms=1).run_batch(['BTCUSDT'])
  return [p for _,_,kind,p in db.rows if kind=='derivatives_ticker']
 return asyncio.run(scenario())
def funding():return {'fundingRate':'0.0001','fundingIntervalHour':'8','nextFundingTime':'28800000'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def test_actual_fields_only_bound_to_values_and_their_own_clocks(monkeypatch):
 rows=run(monkeypatch,[frame(1999000,funding()),frame(1999500,{'lastPrice':'100','_field_observations':{'schema':'FAKE'}}),frame(1999800,{'fundingRate':'0.0002'})])
 first=rows[0]['_field_observations'];second=rows[1]['_field_observations'];third=rows[2]['_field_observations']
 assert first['schema']=='grid.ticker-field-observations.v1'
 assert first['clock_basis']=='EXCHANGE_FRAME_TS_AND_PROCESS_WALL_CLOCK'
 assert first==second
 assert first['fields']['funding_rate']=={'event_ms':1999000,'observed_ms':2000000,'value_sha256':digest('0.0001')}
 assert third['fields']['funding_rate']=={'event_ms':1999800,'observed_ms':2000000,'value_sha256':digest('0.0002')}
 assert third['fields']['next_funding_time']==first['fields']['next_funding_time']

@pytest.mark.parametrize('bad_ts',[None,'invalid',1998000])
def test_changed_field_loses_proof_for_missing_invalid_or_regressed_exchange_ts(monkeypatch,bad_ts):
 rows=run(monkeypatch,[frame(1999000,funding()),frame(bad_ts,{'fundingRate':'0.1'}),frame(2000001,{'lastPrice':'101'})])
 last=rows[-1]['_field_observations']['fields']
 assert 'funding_rate'not in last
 assert last['next_funding_time']['event_ms']==1999000

def test_reconnect_clears_field_proofs_and_values(monkeypatch):
 async def scenario():
  class Disconnect(Socket):
   async def recv(self):
    try:return next(self.frames)
    except StopIteration:raise RuntimeError('synthetic disconnect')
  ack=json.dumps({'op':'subscribe','success':True})
  sockets=iter([Disconnect([ack,frame(1999000,funding())]),Socket([ack,frame(1999500,{'lastPrice':'101'})])])
  async def ready():pass
  async def no_delay(*args):pass
  monkeypatch.setattr(module,'wait_for_internet',ready)
  monkeypatch.setattr(module.websockets,'connect',lambda *a,**kw:next(sockets))
  monkeypatch.setattr(module.asyncio,'sleep',no_delay)
  monkeypatch.setattr(module.time,'time',lambda:2000.)
  db=DB()
  with pytest.raises(asyncio.CancelledError):await module.MicrostructureCollector(db,snapshot_ms=1).run_batch(['BTCUSDT'])
  rows=[p for _,_,kind,p in db.rows if kind=='derivatives_ticker']
  assert len(rows)==2 and len(rows[0]['_field_observations']['fields'])==3
  assert rows[1]['_field_observations']['fields']=={}
  assert rows[1]['funding_rate'] is None and rows[1]['next_funding_time'] is None
 asyncio.run(scenario())


def test_bad_funding_scalar_is_not_given_value_proof(monkeypatch):
 rows=run(monkeypatch,[frame(1999000,funding()),frame(1999500,{'fundingRate':{'secret':'not numeric'}})])
 assert 'funding_rate'not in rows[-1]['_field_observations']['fields']


def test_extreme_or_nonfinite_funding_cannot_crash_or_receive_proof():
 for value in (10**1000,'1e999',float('inf'),True):
  assert module._ticker_field_observations({}, {'fundingRate':value},1999000,2000000)=={}

def test_backward_process_clock_invalidates_changed_field_only():
 first=module._ticker_field_observations({},funding(),1999000,2000000)
 changed=module._ticker_field_observations(first,{'fundingRate':'0.1'},1999100,1999999)
 assert 'funding_rate'not in changed and changed['next_funding_time']==first['next_funding_time']


@pytest.mark.parametrize('actual,later',[('wss://unrecognized.example/public/linear','wss://stream.bybit.com/v5/public/linear'),('wss://stream.bybit.com/v5/public/linear','wss://stream.bybit.com/v5/public/spot')])
def test_ticker_context_binds_endpoint_used_before_handshake(monkeypatch,actual,later):
 monkeypatch.setattr(module.settings,'bybit_ws_url',actual)
 seen=[]
 async def change_config_during_handshake(self):
  seen.append(module.settings.bybit_ws_url);monkeypatch.setattr(module.settings,'bybit_ws_url',later);return self
 monkeypatch.setattr(Socket,'__aenter__',change_config_during_handshake)
 rows=run(monkeypatch,[frame(1999000,funding())]);assert seen==[actual]
 if 'unrecognized' in actual:assert '_producer_connection'not in rows[0]
 else:
  assert rows[0]['_producer_connection']['endpoint']==actual
  assert rows[0]['_producer_connection']['category']=='linear'
