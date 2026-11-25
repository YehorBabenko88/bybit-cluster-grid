"""Retained endpoint obligations on the canonical bounded REST reader; fake bytes only."""
import json
from market_data import market_backfill as api

class Response:
 status=200;headers={}
 def __init__(self,rows):self.body=json.dumps({'retCode':0,'result':{'list':rows}}).encode();self.offset=0;self.content=self
 def raise_for_status(self):pass
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 async def read(self,size):
  out=self.body[self.offset:self.offset+size];self.offset+=len(out);return out
class Session:
 def __init__(self):self.calls=[]
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 def get(self,url,**kwargs):
  self.calls.append((url,kwargs['params']))
  assert kwargs['allow_redirects'] is False
  rows=[]
  if url.endswith('/open-interest'):rows=[{'timestamp':'1','openInterest':'2'}]
  elif url.endswith('/funding/history'):rows=[{'symbol':'BTCUSDT','fundingRateTimestamp':'1','fundingRate':'0.0001'}]
  return Response(rows)
def install(monkeypatch):
 s=Session();monkeypatch.setattr(api.aiohttp,'ClientSession',lambda **kwargs:s)
 monkeypatch.setattr(api.aiohttp,'DummyCookieJar',lambda:None)
 return s
def finish(coro):
 try:coro.send(None)
 except StopIteration as done:return done.value
 else:
  coro.close();raise AssertionError('fake operation unexpectedly suspended')

def test_rich_history_methods_use_explicit_bybit_endpoints(monkeypatch):
 s=install(monkeypatch);base='https://api.bybit.com'
 for dataset in ('mark_price','index_price','premium_index'):
  finish(api.fetch_kline_page(base,'BTCUSDT','1',60000,start_ms=0,dataset=dataset))
 finish(api.fetch_open_interest_page(base,'BTCUSDT','5min',0,60000))
 finish(api.fetch_funding_page(base,'BTCUSDT',0,60000))
 finish(api.fetch_long_short_ratio_page(base,'BTCUSDT',0,60000,'5min'))
 paths=[u.split('api.bybit.com')[-1] for u,_ in s.calls]
 assert paths==[
  '/v5/market/mark-price-kline','/v5/market/index-price-kline','/v5/market/premium-index-price-kline',
  '/v5/market/open-interest','/v5/market/funding/history','/v5/market/account-ratio']

def test_rich_history_uses_endpoint_specific_parameter_names(monkeypatch):
 s=install(monkeypatch);base='https://api.bybit.com'
 finish(api.fetch_kline_page(base,'BTCUSDT','1',2,start_ms=1,dataset='mark_price'))
 finish(api.fetch_open_interest_page(base,'BTCUSDT','5min',1,2))
 finish(api.fetch_long_short_ratio_page(base,'BTCUSDT',1,2,'5min'))
 mark=s.calls[0][1];oi=s.calls[1][1];ratio=s.calls[2][1]
 assert mark['start']==1 and mark['end']==2 and mark['interval']=='1'
 assert 'startTime' not in mark
 assert oi['startTime']==1 and oi['endTime']==2 and oi['intervalTime']=='5min'
 assert ratio['startTime']==1 and ratio['endTime']==2 and ratio['period']=='5min'


import pytest
@pytest.mark.parametrize('changes',[{'symbol':True},{'symbol':'X'*65},{'start_ms':True},{'end_ms':-1},{'start_ms':3,'end_ms':2},{'limit':True},{'limit':501},{'interval':'bad period'},{'interval':'X'*33}])
def test_account_ratio_invalid_inputs_refuse_before_transport(monkeypatch,changes):
 def denied(**kwargs):raise AssertionError('transport construction forbidden')
 monkeypatch.setattr(api.aiohttp,'ClientSession',denied)
 args=dict(base_url='https://api.bybit.com',symbol='BTCUSDT',start_ms=1,end_ms=2,interval='5min',limit=500);args.update(changes)
 with pytest.raises(ValueError):finish(api.fetch_long_short_ratio_page(**args))

def test_account_ratio_raw_precision_not_relabelled_numeric_validation(monkeypatch):
 class Raw(Session):
  def get(self,url,**kwargs):
   super().get(url,**kwargs)
   return Response([{'symbol':'BTCUSDT','buyRatio':'0.10000000000000000001','sellRatio':'1e-1000','timestamp':'1'}])
 s=Raw();monkeypatch.setattr(api.aiohttp,'ClientSession',lambda **kwargs:s);monkeypatch.setattr(api.aiohttp,'DummyCookieJar',lambda:None)
 result=finish(api.fetch_long_short_ratio_page('https://api.bybit.com','BTCUSDT',1,2))
 assert result[0]['buyRatio']=='0.10000000000000000001' and result[0]['sellRatio']=='1e-1000'

@pytest.mark.parametrize('values',[[{},{}],[['invalid']]])
def test_account_ratio_row_cap_and_shape_before_return(monkeypatch,values):
 class Bad(Session):
  def get(self,*args,**kwargs):return Response(values)
 monkeypatch.setattr(api.aiohttp,'ClientSession',lambda **kwargs:Bad());monkeypatch.setattr(api.aiohttp,'DummyCookieJar',lambda:None)
 with pytest.raises(ValueError):finish(api.fetch_long_short_ratio_page('https://api.bybit.com','BTCUSDT',1,2,limit=1))
