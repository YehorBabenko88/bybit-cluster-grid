import asyncio
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
import pytest
from grid.fenced_ingest import ingest_owned,OwnershipExpired
from grid.collection_ownership import wal_envelope


def test_delayed_ttl_response_does_not_extend_symbol_commit_permission():
    async def run():
        session=uuid.uuid4()
        payload=wal_envelope({'symbol':'BTCUSDT','value':1},{'generation':1,'session':str(session)})
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        expiry=asyncio.get_running_loop().time()+.4
        committed=[]
        class Connection:
            async def execute(self,*args):pass
            async def fetchrow(self,sql,*args):
                if 'FROM collection_ingest_receipts' in sql:return {'sha256':digest,'disposition':'PENDING'}
                return {'owner':'node','session':session,'generation':1}
            async def fetchval(self,sql,*args):
                if 'extract(epoch' in sql:
                    remaining=expiry-asyncio.get_running_loop().time()
                    await asyncio.sleep(.2)
                    return remaining
                return asyncio.get_running_loop().time()<expiry
            @asynccontextmanager
            async def transaction(self):
                yield
                await asyncio.sleep(.3)
                committed.append(True)
        class Pool:
            @asynccontextmanager
            async def acquire(self):yield Connection()
        async def persist(*args):pass
        with pytest.raises(OwnershipExpired):await ingest_owned(Pool(),'node','minute',payload,persist)
        assert committed==[]
    asyncio.run(run())
