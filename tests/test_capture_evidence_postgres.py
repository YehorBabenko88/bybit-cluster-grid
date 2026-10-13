import asyncio
import os
import uuid
import pytest
from grid.collection_ownership import grant_assignments,wal_envelope
from grid.fenced_ingest import ingest_owned
from test_collection_ownership_postgres import database

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database only')


@pytest.mark.parametrize('kind',['public_trade_capture_evidence','orderbook_capture_evidence'])
def test_even_current_capture_evidence_is_quarantined_and_deduplicated(kind):
    async def run():
        async with database() as pool:
            grant=(await grant_assignments(pool,'node',str(uuid.uuid4()),['BTCUSDT']))['BTCUSDT']
            row=wal_envelope({'symbol':'BTCUSDT','event_type':kind,'event_ts':1700000000123,
                             'payload':{'capture_stage':'PRE_AGGREGATION','raw':'x'*20000}},grant)
            async def forbidden(*args):raise AssertionError('evidence reached canonical writer')
            replies=await asyncio.gather(ingest_owned(pool,'node','event',row,forbidden),
                                         ingest_owned(pool,'node','event',row,forbidden))
            assert all(r['disposition']=='QUARANTINED' for r in replies)
            assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==1
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
    asyncio.run(run())
