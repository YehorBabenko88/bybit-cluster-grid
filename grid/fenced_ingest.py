"""Atomic ownership gate, immutable receipts and durable stale-WAL quarantine."""
from contextlib import asynccontextmanager
import hashlib
import json
import uuid
import asyncio


class ConnectionPool:
    """Keep existing persistence APIs on the already fenced transaction."""
    def __init__(self,connection):self.connection=connection
    @asynccontextmanager
    async def acquire(self):yield self.connection
    def __getattr__(self,name):return getattr(self.connection,name)


class OwnershipExpired(ValueError):pass


async def ingest_owned(pool,node_id,kind,payload,persist):
    try:
        async with asyncio.timeout(None) as deadline:
            return await _ingest_owned(pool,node_id,kind,payload,persist,deadline)
    except TimeoutError as exc:
        raise OwnershipExpired('collection lease expired during transaction commit') from exc


async def _ingest_owned(pool,node_id,kind,payload,persist,deadline):
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    record_id=payload.get('delivery_id') or 'legacy:'+digest
    if not isinstance(record_id,str) or len(record_id)>128:
        raise ValueError('invalid delivery ID')
    symbol=payload.get('symbol')
    if not isinstance(symbol,str) or not symbol:
        raise ValueError('invalid collection symbol')
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute("""INSERT INTO collection_ingest_receipts
              (node_id,kind,record_id,sha256,symbol,payload,disposition)
              VALUES($1,$2,$3,$4,$5,$6::jsonb,'PENDING') ON CONFLICT DO NOTHING""",
              node_id,kind,record_id,digest,symbol,raw)
            receipt=await c.fetchrow("""SELECT sha256,disposition FROM collection_ingest_receipts
              WHERE node_id=$1 AND kind=$2 AND record_id=$3 FOR UPDATE""",node_id,kind,record_id)
            if receipt['sha256']!=digest:
                raise ValueError('delivery ID reused with different bytes')
            disposition=receipt['disposition']
            if disposition=='PENDING':
                row=await c.fetchrow("SELECT * FROM collection_ownership WHERE symbol=$1 FOR UPDATE",symbol)
                lease_live=bool(row and await c.fetchval("SELECT lease_until>clock_timestamp() FROM collection_ownership WHERE symbol=$1",symbol))
                token=payload.get('ownership')
                token=token if isinstance(token,dict) else {}
                try:session=uuid.UUID(str(token.get('session')))
                except (ValueError,TypeError,AttributeError):session=None
                generation=token.get('generation')
                live=bool(row and lease_live and row['owner']==node_id and session is not None
                          and row['session']==session and type(generation) is int
                          and row['generation']==generation)
                disposition='LIVE' if live else 'QUARANTINED'
                if live:
                    ttl=await c.fetchval("SELECT extract(epoch from lease_until-clock_timestamp()) FROM collection_ownership WHERE symbol=$1",symbol)
                    if ttl<=0:raise OwnershipExpired('collection lease expired before persistence')
                    deadline.reschedule(asyncio.get_running_loop().time()+float(ttl))
                    await persist(ConnectionPool(c),payload)
                    # now() is transaction-start time and is unsafe after a stall.
                    if not await c.fetchval("SELECT lease_until>clock_timestamp() FROM collection_ownership WHERE symbol=$1",symbol):
                        raise OwnershipExpired('collection lease expired during persistence')
                await c.execute("""UPDATE collection_ingest_receipts SET disposition=$4
                  WHERE node_id=$1 AND kind=$2 AND record_id=$3""",node_id,kind,record_id,disposition)
    return {'ok':True,'ownership_protocol':1,'disposition':disposition,'sha256':digest}
