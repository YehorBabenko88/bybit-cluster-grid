import copy
import importlib.util
from pathlib import Path

import pytest


def gate(now=10):
    path=Path(__file__).resolve().parents[1]/'s0_smoke'/'subscription.py'
    assert path.is_file(), 'pure subscription gate must exist'
    spec=importlib.util.spec_from_file_location('s0_subscription_test',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod.SubscriptionGate(now)


def frame(topic='orderbook.1.BTCUSDT'):
    return {'topic':topic,'type':'snapshot','data':{'s':'BTCUSDT'}}


def ack(): return {'op':'subscribe','success':True,'req_id':'S0'}


def test_preack_buffer_releases_once_in_arrival_order():
    g=gate(); a=frame(); b=frame('publicTrade.BTCUSDT')
    assert not g.acknowledged
    assert g.feed(a,10.1)==[]
    assert g.feed(b,10.2)==[]
    assert not g.acknowledged
    assert g.feed(ack(),10.3)==[a,b]
    assert g.acknowledged
    assert g.feed(frame(),10.4)==[frame()]


def test_freezes_before_ack_and_returns_independent_postack_copy():
    g=gate(); a=frame(); original=copy.deepcopy(a)
    g.feed(a,10);a['data']['s']='private';a['topic']='order'
    assert g.feed(ack(),11)==[original]
    b=frame();released=g.feed(b,11.1);b['data']['s']='changed'
    assert released==[original]


@pytest.mark.parametrize('value',[{'op':'subscribe','success':False,'req_id':'S0'},
    {'op':'subscribe','success':1,'req_id':'S0'}, {'op':'subscribe','success':True,'req_id':'wrong'},
    {'op':'auth'}, {'op':'order.create'}, {'op':'unknown'}, {'topic':'order'},
    {'topic':'publicTrade.ETHUSDT'}, {'topic':'orderbook.50.BTCUSDT'}, {'op':'subscribe'}, [], None])
def test_rejects_wrong_ack_or_private_or_unknown_input(value):
    g=gate()
    with pytest.raises(ValueError,match='^S0_'):g.feed(value,10.1)
    assert not g.acknowledged


def test_duplicate_ack_is_rejected():
    g=gate();g.feed(ack(),10)
    with pytest.raises(ValueError,match='^S0_'):g.feed(ack(),10.1)


def test_frame_count_limit():
    g=gate()
    for _ in range(8):assert g.feed(frame(),10)==[]
    with pytest.raises(ValueError,match='^S0_'):g.feed(frame(),10)
    assert not g.acknowledged


def test_total_byte_limit():
    g=gate(); large=frame();large['data']['padding']='x'*800000
    g.feed(large,10);g.feed(large,10)
    with pytest.raises(ValueError,match='^S0_'):g.feed(large,10)
    assert not g.acknowledged


def test_deadline_ping_cannot_extend_and_exact_boundary_ack_is_allowed():
    g=gate()
    assert g.feed({'op':'ping','req_id':'S0'},11)==[]
    assert g.feed({'op':'pong'},12)==[]
    with pytest.raises(ValueError,match='^S0_'):g.check(12.001)
    g=gate();assert g.feed(ack(),12)==[]
    g.check(100)


@pytest.mark.parametrize('now',[9,True,float('nan'),float('inf'),-1,'11'])
def test_bad_clock_rejected(now):
    g=gate()
    with pytest.raises(ValueError,match='^S0_'):g.check(now)


def test_regression_after_progress_and_missing_ack_never_release():
    g=gate();g.feed(frame(),11)
    with pytest.raises(ValueError,match='^S0_'):g.feed(ack(),10.9)
    assert not g.acknowledged
    with pytest.raises(ValueError,match='^S0_'):g.feed(ack(),12.1)
    assert not g.acknowledged


def test_json_nonfinite_or_oversized_frame_is_rejected():
    for bad in [float('nan'),'x'*1048576]:
        g=gate();msg=frame();msg['data']['bad']=bad
        with pytest.raises(ValueError,match='^S0_'):g.feed(msg,10)
