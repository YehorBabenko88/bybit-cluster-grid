import asyncio
import hashlib
import json
from types import SimpleNamespace
import pytest
from grid.micro_event_storage import MicroEventStorage


@pytest.mark.parametrize('disposition,protocol,status,accepted',[
    ('LIVE',None,200,False),('QUARANTINED',None,200,False),
    ('QUARANTINED',1,404,False),('LIVE',1,200,False),
    ('QUARANTINED',True,200,False),
    ('QUARANTINED',1,200,True)])
def test_capture_replay_requires_dedicated_route_and_protocol_receipt(monkeypatch,disposition,protocol,status,accepted):
    from grid import credential_store
    monkeypatch.setattr(credential_store,'node_credential',lambda:'test')
    async def run():
        row={'symbol':'BTCUSDT','event_type':'public_trade_capture_evidence','event_ts':1,
             'payload':{},'delivery_id':'capture','ownership':{'generation':1,'session':'old'}}
        digest=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        acknowledgements=[];paths=[]
        class Reply:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def json(self):return {'ownership_protocol':1,'disposition':disposition,'sha256':digest,
                                        'capture_evidence_protocol':protocol}
        Reply.status=status
        class HTTP:
            def post(self,path,**kwargs):paths.append(path);return Reply()
        async def ack(record):acknowledgements.append(record)
        sink=MicroEventStorage.__new__(MicroEventStorage)
        sink.replay_ids=set();sink.http=HTTP();sink.spool=SimpleNamespace(ack=ack)
        if accepted:await sink._save_spooled(1,row)
        else:
            with pytest.raises(RuntimeError):await sink._save_spooled(1,row)
        assert paths[0].endswith('/ingest/capture')
        assert acknowledgements==([1] if accepted else [])
    asyncio.run(run())
