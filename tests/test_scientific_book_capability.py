"""Offline feed/capability regressions; no real websocket or database."""
import asyncio
import copy
import json
import time
from datetime import datetime,timezone

import pytest

from grid import microstructure as module
from grid.unified_features import UnifiedFeatureBuilder


class RecordingDB:
    def __init__(self): self.events=[]
    async def insert_event(self,symbol,ts,kind,payload):
        self.events.append((symbol,kind,payload))


class Socket:
    def __init__(self,frames): self.frames=iter(frames)
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return None
    async def send(self,_): pass
    async def recv(self):
        try: return next(self.frames)
        except StopIteration: raise asyncio.CancelledError


def frame(ts,seq,kind,bids,asks):
    return json.dumps({'topic':'orderbook.50.BTCUSDT','type':kind,'ts':ts,
                       'data':{'seq':seq,'u':seq-90,'b':bids,'a':asks}})


def collect(monkeypatch,frames):
    async def run():
        async def ready(): pass
        socket=Socket([json.dumps({'op':'subscribe','success':True}),*frames])
        monkeypatch.setattr(module,'wait_for_internet',ready)
        monkeypatch.setattr(module.websockets,'connect',lambda *a,**kw:socket)
        db=RecordingDB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(['BTCUSDT'])
        return [payload for _,kind,payload in db.events if kind=='orderbook_snapshot']
    return asyncio.run(run())


@pytest.mark.parametrize('bids,asks',[([],[]),([['100','1']],[]),([],[['101','2']])])
def test_incomplete_snapshot_never_publishes_available_book(monkeypatch,bids,asks):
    now=int(time.time()*1000)
    images=collect(monkeypatch,[frame(now,100,'snapshot',bids,asks),
        frame(now+1000,101,'snapshot',[['100','1']],[['101','2']])])
    assert [p['sequence'] for p in images]==[101]
    assert images[0]['_quality']['feeds']['orderbook']['status']=='available'
    assert images[0]['spread']==1


@pytest.mark.parametrize('bids,asks',[([['100','0']],[]),([],[['101','0']])])
def test_delta_emptying_one_side_requires_fresh_snapshot(monkeypatch,bids,asks):
    now=int(time.time()*1000)
    images=collect(monkeypatch,[
        frame(now,100,'snapshot',[['100','1']],[['101','2']]),
        frame(now+1000,101,'delta',bids,asks),
        frame(now+2000,102,'delta',[['100','3']],[['101','4']]),
        frame(now+3000,103,'snapshot',[['100','5']],[['101','6']])])
    assert [p['sequence'] for p in images]==[100,103]
    assert images[-1]['bid_depth']==5 and images[-1]['ask_depth']==6


def good_payload():
    return {'_quality':{'feeds':{'orderbook':{'status':'available','reason':None}}},
            'book':{'bids':[[100,1]],'asks':[[101,2]]},
            'best_bid':100,'best_ask':101,'spread':1,'bid_depth':1,'ask_depth':2,
            'imbalance':-1/3,'sequence':100,'update_id':10}


def build(payload):
    async def run():
        row={'symbol':'BTCUSDT','ts':datetime.now(timezone.utc),'open':100,'high':102,
             'low':99,'close':101,'buy_volume':8,'sell_volume':2,'delta':6,
             'poc_price':100,'quality_status':'GOOD'}
        class Pool:
            async def fetchrow(self,sql,*args):
                return {'event_ts':row['ts'],'payload':payload} if 'orderbook_snapshot' in sql else None
        return await UnifiedFeatureBuilder().build(Pool(),row)
    return asyncio.run(run())


@pytest.mark.parametrize('quality',[None,{},'available',{'feeds':None},
    {'feeds':{'orderbook':None}},
    *[{'feeds':{'orderbook':{'status':s}}} for s in
      ('missing','stale','gap','unavailable','degraded','unknown','AVAILABLE',True)]])
def test_legacy_or_explicit_bad_quality_masks_book_metrics(quality):
    payload=good_payload()
    if quality is None: payload.pop('_quality')
    else: payload['_quality']=quality
    built=build(payload)
    assert built['capabilities']['orderbook'] is False
    for key in ('book_imbalance','spread','bid_depth','ask_depth'):
        assert built['features'][key] is None


@pytest.mark.parametrize('book',[None,{}, {'bids':[],'asks':[[101,2]]},
    {'bids':[[100,1]],'asks':[]},{'bids':[[102,1]],'asks':[[101,2]]},
    {'bids':[[100,0]],'asks':[[101,2]]}])
def test_available_flag_without_complete_valid_sides_is_not_capability(book):
    payload=good_payload();payload['book']=book
    built=build(payload)
    assert built['capabilities']['orderbook'] is False
    assert built['features']['spread'] is None


def test_valid_existing_producer_payload_preserves_book_features():
    payload=good_payload();before=copy.deepcopy(payload)
    built=build(payload)
    assert built['capabilities']['orderbook'] is True
    assert built['features']['spread']==1
    assert built['features']['bid_depth']==1 and built['features']['ask_depth']==2
    assert payload==before


@pytest.mark.parametrize('side,index',[('bids',0),('bids',1),('asks',0),('asks',1)])
def test_boolean_price_or_quantity_cannot_enable_capability(side,index):
    payload=good_payload();payload['book'][side][0][index]=True
    built=build(payload)
    assert built['capabilities']['orderbook'] is False
    assert built['features']['spread'] is None
