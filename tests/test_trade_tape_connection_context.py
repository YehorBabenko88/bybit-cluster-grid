"""Synthetic sockets only; no exchange or process-identity attestation."""
import asyncio,json
from types import SimpleNamespace
import pytest
from grid import worker as module,microstructure
from grid.micro_tape import MicroTapeAggregator
from test_public_trade_stream_admission import ACK,frame


def test_only_closed_actual_public_endpoints_receive_declared_context():
 for category in ('linear','inverse','spot'):
  endpoint='wss://stream.bybit.com/v5/public/'+category
  first=microstructure.public_market_connection(endpoint);second=microstructure.public_market_connection(endpoint)
  assert first['category']==category and first['endpoint']==endpoint
  assert first['connection_id']!=second['connection_id']
  assert first['scope']=='PRODUCER_DECLARED_LOCAL_CONNECTION_NOT_REMOTE_AUTHENTICATION'
 for endpoint in ('wss://evil.example/linear','https://stream.bybit.com/v5/public/linear','wss://stream.bybit.com/v5/public/linear?extra=1'):
  assert microstructure.public_market_connection(endpoint)is None

def test_trade_reconnect_discards_only_own_open_bucket_and_attaches_actual_context(monkeypatch):
 async def scenario():
  contexts=[];original=microstructure.public_market_connection
  def capture(endpoint):
   value=original(endpoint);contexts.append(value);return value
  monkeypatch.setattr(microstructure,'public_market_connection',capture)
  class Socket:
   def __init__(self,items,disconnect=False):self.items=iter(items);self.disconnect=disconnect
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def send(self,*args):pass
   async def recv(self):
    try:return json.dumps(next(self.items))
    except StopIteration:
     if self.disconnect:raise RuntimeError('synthetic reconnect')
     raise asyncio.CancelledError
  injected=frame(stamp=600250,price='200',trade_id='fresh');injected['_producer_connection']={'connection_id':'FAKE'}
  sockets=iter([Socket([ACK,frame(stamp=600000,price='100',trade_id='old')],True),Socket([ACK,injected,frame(stamp=600500,price='300',trade_id='next')])])
  async def ready():pass
  monkeypatch.setattr(module,'wait_for_internet',ready);monkeypatch.setattr(module.asyncio,'sleep',lambda *a:ready())
  monkeypatch.setattr(module.websockets,'connect',lambda *a,**kw:next(sockets));monkeypatch.setattr(module.time,'time',lambda:600.75)
  monkeypatch.setattr(module.settings,'bybit_ws_url','wss://stream.bybit.com/v5/public/linear')
  class Storage:
   def __init__(self):self.rows=[]
   async def save(self,row):self.rows.append(row)
   async def insert_event(self,*row):self.rows.append(row)
  worker=module.Worker.__new__(module.Worker);worker.meta={'BTCUSDT':{'tick_size':.1}};worker.micro_wanted={'BTCUSDT'}
  worker.storage=Storage();worker.micro_storage=Storage();worker.micro_tape=MicroTapeAggregator(250)
  worker.micro_tape.state['ETHUSDT']={'preserved':'foreign symbol'};worker.micro_tape.cvd['ETHUSDT']=7
  worker.pressure=SimpleNamespace(state='NORMAL',bad_ticks=0,observe_symbol=lambda *a,**kw:None)
  with pytest.raises(asyncio.CancelledError):await worker.trade_stream('BTCUSDT')
  rows=worker.micro_storage.rows
  assert len(rows)==1 and rows[0][1]==600250
  assert rows[0][3]['open']==200 and rows[0][3]['trade_count']==1 and rows[0][3]['cvd']==2
  assert len(contexts)==2 and contexts[0]['connection_id']!=contexts[1]['connection_id']
  assert rows[0][3]['_producer_connection']==contexts[1]
  assert worker.micro_tape.state['ETHUSDT']=={'preserved':'foreign symbol'} and worker.micro_tape.cvd['ETHUSDT']==7
 asyncio.run(scenario())


@pytest.mark.parametrize('actual,later',[('wss://unrecognized.example/public/linear','wss://stream.bybit.com/v5/public/linear'),('wss://stream.bybit.com/v5/public/linear','wss://stream.bybit.com/v5/public/spot')])
def test_trade_context_binds_endpoint_used_before_handshake(monkeypatch,actual,later):
 from test_public_trade_stream_admission import run,Socket
 async def scenario():
  monkeypatch.setattr(module.settings,'bybit_ws_url',actual);seen=[];events=[]
  async def change_config_during_handshake(self):
   seen.append(module.settings.bybit_ws_url);monkeypatch.setattr(module.settings,'bybit_ws_url',later);return self
  monkeypatch.setattr(Socket,'__aenter__',change_config_during_handshake)
  class Micro:
   async def insert_event(self,*args):events.append(args)
  def setup(worker):
   worker.micro_wanted={'BTCUSDT'};worker.micro_tape=MicroTapeAggregator(250);worker.micro_storage=Micro()
  await run(monkeypatch,[ACK,frame(stamp=600000,trade_id='first'),frame(stamp=600250,trade_id='closed')],clock=[600.5],setup=setup)
  assert seen==[actual] and len(events)==1
  payload=events[0][3]
  if 'unrecognized'in actual:assert '_producer_connection'not in payload
  else:
   assert payload['_producer_connection']['endpoint']==actual
   assert payload['_producer_connection']['category']=='linear'
 asyncio.run(scenario())
