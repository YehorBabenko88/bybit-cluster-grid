"""Persisted collector ownership and immutable, conservative local grants."""
import copy
import json
import math
import time
import uuid
import hashlib

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS collection_ownership(
    symbol text PRIMARY KEY, owner text, session uuid,
    generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0),
    lease_until timestamptz NOT NULL DEFAULT '-infinity')""",
    """CREATE TABLE IF NOT EXISTS collection_ingest_receipts(
    node_id text NOT NULL,kind text NOT NULL,record_id text NOT NULL,
    sha256 text NOT NULL,symbol text NOT NULL,payload jsonb NOT NULL,
    disposition text NOT NULL CHECK(disposition IN ('PENDING','LIVE','QUARANTINED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(node_id,kind,record_id))""",
    "CREATE INDEX IF NOT EXISTS collection_quarantine_idx ON collection_ingest_receipts(disposition,created_at)",
]


async def grant_assignments(pool,node_id,session,symbols,lease_seconds=30):
    """Desired placement is not a grant: never steal a live process lease."""
    try:
        session=uuid.UUID(str(session))
    except (ValueError,TypeError,AttributeError):
        return {}
    if not node_id or not math.isfinite(lease_seconds) or lease_seconds<=2:
        raise ValueError("invalid collection lease")
    grants={}
    async with pool.acquire() as c:
        async with c.transaction():
            for symbol in sorted(set(symbols)):
                await c.execute("INSERT INTO collection_ownership(symbol) VALUES($1) ON CONFLICT DO NOTHING",symbol)
                row=await c.fetchrow("SELECT * FROM collection_ownership WHERE symbol=$1 FOR UPDATE",symbol)
                # SELECT expressions may run before the row-lock wait. Obtain
                # the database clock only after the lock has actually arrived.
                live=await c.fetchval("SELECT lease_until>clock_timestamp() FROM collection_ownership WHERE symbol=$1",symbol)
                same=row['owner']==node_id and row['session']==session
                if live and not same:
                    continue
                generation=row['generation'] if live and same else row['generation']+1
                if generation>=2**63:
                    raise ValueError("collection generation exhausted")
                updated=await c.fetchrow("""UPDATE collection_ownership
                  SET owner=$2,session=$3,generation=$4,
                      lease_until=clock_timestamp()+($5*interval '1 second')
                  WHERE symbol=$1 RETURNING generation,
                  extract(epoch from lease_until-clock_timestamp()) AS ttl""",
                  symbol,node_id,session,generation,float(lease_seconds))
                grants[symbol]={"generation":updated['generation'],"session":str(session),
                                "ttl_seconds":float(updated['ttl'])}
    return grants


def local_grants(reply,session,request_started,now=None):
    """TTL starts before the request, not when a delayed response arrives."""
    current=time.monotonic() if now is None else now
    if reply.get('ownership_protocol')!=1:
        return {}
    out={}
    for symbol,grant in (reply.get('ownership') or {}).items():
        if not isinstance(grant,dict) or grant.get('session')!=session:
            continue
        generation=grant.get('generation'); ttl=grant.get('ttl_seconds')
        if type(generation) is not int or not 0<generation<2**63 or type(ttl) not in (int,float):
            continue
        if not math.isfinite(ttl) or ttl<=1:
            continue
        deadline=request_started+ttl-1
        if current<deadline:
            out[symbol]={"generation":generation,"session":session,"deadline":deadline}
    return out


class OwnedSink:
    """A collector's grant cannot change when a later heartbeat takes over."""
    def __init__(self,sink,grants,renewals=None):
        self.sink=sink;self.grants=copy.deepcopy(grants);self.renewals=renewals
        self.started_ms=int(time.time()*1000)

    def token(self,symbol):
        grant=self.grants.get(symbol)
        if grant and self.renewals is not None:
            renewed=self.renewals.get(symbol)
            if not renewed or any(renewed.get(k)!=grant.get(k) for k in ('generation','session')):
                raise ValueError("collector ownership expired")
            grant=renewed
        if not grant or time.monotonic()>=grant['deadline']:
            raise ValueError("collector ownership expired")
        return {"generation":grant['generation'],"session":grant['session']}

    async def save(self,row):
        if type(row.get('start_ms')) is int and row['start_ms']<self.started_ms:
            row={**row,'quality_status':'DEGRADED',
                 'quality_reasons':list(dict.fromkeys([*row.get('quality_reasons',[]),'ownership_partial_start']))}
        await self.sink.save(row,ownership=self.token(row['symbol']))

    async def insert_event(self,symbol,event_ts,event_type,payload):
        await self.sink.insert_event(symbol,event_ts,event_type,payload,
                                     ownership=self.token(symbol))

    async def capture_event(self,symbol,event_ts,event_type,payload):
        await self.insert_event(symbol,event_ts,event_type,payload)


def wal_envelope(row,ownership=None):
    # Stamp exactly once before durable append, never on replay/send.
    result=dict(row)
    result['delivery_id']=str(uuid.uuid4())
    if ownership is not None:
        result['ownership']=dict(ownership)
    return result


async def check_receipt(resp,payload):
    if resp.status!=200:
        raise RuntimeError("CONTROL ingest rejected: "+str(resp.status))
    receipt=await resp.json()
    if receipt.get('ownership_protocol')!=1 or receipt.get('disposition') not in ('LIVE','QUARANTINED'):
        raise RuntimeError("CONTROL did not return a durable ownership receipt")
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if receipt.get('sha256')!=digest:
        raise RuntimeError("CONTROL receipt does not match WAL bytes")
    return receipt
