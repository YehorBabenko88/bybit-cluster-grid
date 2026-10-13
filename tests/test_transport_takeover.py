import asyncio
from grid.config import settings
from grid.ml_transport_client import MLTransportClient


def test_actual_ml_transport_uses_active_endpoint_after_takeover(monkeypatch):
    import aiohttp
    monkeypatch.setattr(settings,'coordinator_url','http://standby:8765')
    monkeypatch.setattr(settings,'coordinator_candidates',['http://standby:8765','http://active:8765'])
    from grid import credential_store
    monkeypatch.setattr(credential_store,'node_credential',lambda:'test')
    posts=[]
    class Reply:
        def __init__(self,status,payload):self.status=status;self.payload=payload
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def raise_for_status(self):
            if self.status!=200:raise RuntimeError('standby 503')
        async def json(self):return self.payload
    class HTTP:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def get(self,url,**kwargs):
            assert kwargs.get('allow_redirects') is False
            assert not kwargs.get('headers')
            return Reply(200,{'ok':True,'control_leader':url.startswith('http://active:'),
                              'control_epoch':2,'control_owner':'active'})
        def request(self,method,url,**kwargs):
            posts.append(url)
            return Reply(200 if url.startswith('http://active:') else 503,{'job':{'id':'safe'}})
    monkeypatch.setattr(aiohttp,'ClientSession',HTTP)
    result=asyncio.run(MLTransportClient('node',session=HTTP()).claim())
    assert result=={'id':'safe'}
    assert posts==['http://active:8765/ml/claim']
