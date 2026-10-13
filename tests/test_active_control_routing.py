import asyncio
from grid.config import settings
from grid.active_control import active_control_url,ControlUnavailable
import pytest


def test_takeover_routes_to_current_leader_without_post_retries(monkeypatch):
    monkeypatch.setattr(settings,'coordinator_candidates',['http://old:8765','http://new:8765'])
    state={'http://old:8765':True,'http://new:8765':False};probes=[]
    async def probe(url):
        probes.append(url)
        return {'ok':True,'control_leader':state[url],'control_epoch':10,'control_owner':url}
    async def run():
        assert await active_control_url(probe=probe)=='http://old:8765'
        state.update({'http://old:8765':False,'http://new:8765':True})
        assert await active_control_url(probe=probe)=='http://new:8765'
        state['http://old:8765']=True
        with pytest.raises(ControlUnavailable):await active_control_url(probe=probe)
        state.update({'http://old:8765':False,'http://new:8765':False})
        with pytest.raises(ControlUnavailable):await active_control_url(probe=probe)
    asyncio.run(run())
    assert len(probes)==8


@pytest.mark.parametrize('url',['https://user:password@control','https://control/path','https://control?token=secret','file:///control'])
def test_invalid_candidate_is_rejected_before_probe(monkeypatch,url):
    monkeypatch.setattr(settings,'coordinator_candidates',[url])
    async def probe(*args):raise AssertionError('invalid address probed')
    with pytest.raises(ValueError):asyncio.run(active_control_url(probe=probe))


def test_single_endpoint_configuration_remains_compatible(monkeypatch):
    monkeypatch.setattr(settings,'coordinator_candidates',[])
    monkeypatch.setattr(settings,'coordinator_url','http://single:8765')
    assert asyncio.run(active_control_url())=='http://single:8765'
