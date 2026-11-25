"""Fake persistent SQL session fault model; no real database/network/process."""
import copy,gzip,hashlib,json
from contextlib import asynccontextmanager
from decimal import Decimal
import pytest
from market_data.archive_import import ArchiveImporter
from market_data.capture_store import CaptureStore
from market_data.segment_wal import SegmentWAL
from market_data.public_trades import Trade,delivery_identity
from market_data.raw_capture import decode_observation

class Connection:
    def __init__(self,state,*,fail_before=False,unknown_commit=False):
        self.info=type("Info",(),{"transaction_status":0})();self.state=state;self.pending=None;self.closed=False;self.fail_before=fail_before;self.unknown_commit=unknown_commit
    @asynccontextmanager
    async def transaction(self):
        before=copy.deepcopy(self.state)
        try:
            yield self
            if self.fail_before and self.state!=before:raise OSError('synthetic rollback before commit')
        except BaseException:self.state.clear();self.state.update(before);raise
        if self.unknown_commit and self.state!=before:
            self.unknown_commit=False
            raise OSError('synthetic committed but acknowledgement lost')
    async def execute(self,sql,p=()):
        if 'archive:read_checkpoint' in sql:self.pending=self.state['checkpoints'].get(p[0])
        elif 'archive:read_event' in sql:self.pending=self.state['events'].get(p[0])
        elif 'archive:insert_event' in sql:self.state['events'].setdefault(p[0],p[1:])
        elif 'archive:read_observation' in sql:self.pending=self.state['observations'].get(p[0])
        elif 'archive:insert_observation' in sql:self.state['observations'].setdefault(p[0],(p[1],None))
        elif 'archive:write_checkpoint' in sql:self.state['checkpoints'][p[0]]=p[1:]
        else:raise AssertionError('unexpected SQL operation')
        return self
    async def fetchone(self):return self.pending
    async def close(self):self.closed=True

def fixture(tmp_path,rows=None):
    root=tmp_path/'blobs';root.mkdir(exist_ok=True)
    data=('trdMatchID,timestamp,price,size,side,symbol\n'+(rows or 'one,1735689600.000001,1.0,0.1,Buy,BTCUSDT\ntwo,1735689600.000002,1,1e-1000,Sell,BTCUSDT\n')).encode()
    payload=gzip.compress(data,mtime=0);path=root/'history.csv.gz';path.write_bytes(payload)
    return root,'history.csv.gz',hashlib.sha256(payload).hexdigest(),len(payload)
def state():return dict(checkpoints={},events={},observations={})
def owner(tmp_path,root,persistent,**faults):
    wal=SegmentWAL(tmp_path/'wal',max_bytes=2**20,segment_bytes=4096)
    connection=Connection(persistent,**faults)
    return ArchiveImporter(root,CaptureStore(connection),wal,source_revision='a'*40),wal,connection

@pytest.mark.asyncio
async def test_archive_exact_events_and_checkpoint_commit_together(tmp_path):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,connection=owner(tmp_path,root,persistent)
    receipt=await importer.ingest(locator,sha,size,'BTCUSDT',batch_size=1)
    assert receipt['committed_source_rows']==2 and receipt['source_authenticity']=='UNKNOWN'
    assert receipt['point_in_time_availability']=='UNKNOWN' and receipt['execution_authority'] is False
    assert len(persistent['events'])==len(persistent['observations'])==2 and wal.recover()==[]
    assert sorted(row[1] for row in persistent['events'].values())==['1735689600000001','1735689600000002']
    assert all(decode_observation(raw)['source_kind']=='ARCHIVE' for raw,_ in persistent['observations'].values())
    assert all(decode_observation(raw)['schema']=='market_data.raw-capture-observation.v2' for raw,_ in persistent['observations'].values())

@pytest.mark.asyncio
async def test_rollback_keeps_events_and_checkpoint_unchanged_and_wal_pending(tmp_path):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,connection=owner(tmp_path,root,persistent,fail_before=True)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT')
    assert persistent==state() and len(wal.recover())==1
    assert connection.closed

@pytest.mark.asyncio
async def test_unknown_commit_restart_replay_is_idempotent_and_then_acknowledges(tmp_path):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,connection=owner(tmp_path,root,persistent,unknown_commit=True)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT')
    assert len(persistent['events'])==2 and len(wal.recover())==1 and connection.closed
    before=copy.deepcopy(persistent);fresh,wal2,_=owner(tmp_path,root,persistent)
    receipt=await fresh.ingest(locator,sha,size,'BTCUSDT')
    assert persistent==before and wal2.recover()==[] and receipt['committed_source_rows']==2

@pytest.mark.asyncio
async def test_blob_hash_drift_after_unknown_commit_blocks_replay_and_checkpoint_ack(tmp_path):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,_=owner(tmp_path,root,persistent,unknown_commit=True)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT')
    before=copy.deepcopy(persistent);(root/locator).write_bytes(b'changed')
    fresh,wal2,_=owner(tmp_path,root,persistent)
    with pytest.raises(ValueError):await fresh.recover()
    assert persistent==before and len(wal2.recover())==1

@pytest.mark.asyncio
async def test_duplicate_source_rows_keep_row_checkpoint_without_duplicate_event(tmp_path):
    row='one,1735689600.000001,1,0.1,Buy,BTCUSDT\n'
    root,locator,sha,size=fixture(tmp_path,row+row);persistent=state();importer,_,_=owner(tmp_path,root,persistent)
    receipt=await importer.ingest(locator,sha,size,'BTCUSDT',batch_size=1)
    assert receipt['committed_source_rows']==2 and len(persistent['events'])==1

@pytest.mark.asyncio
async def test_conflicting_id_cannot_advance_next_checkpoint(tmp_path):
    rows='one,1735689600.000001,1,0.1,Buy,BTCUSDT\none,1735689600.000002,1,0.1,Buy,BTCUSDT\n'
    root,locator,sha,size=fixture(tmp_path,rows);persistent=state();importer,wal,_=owner(tmp_path,root,persistent)
    with pytest.raises(ValueError):await importer.ingest(locator,sha,size,'BTCUSDT',batch_size=1)
    assert len(persistent['events'])==1 and next(iter(persistent['checkpoints'].values()))[1]==1
    assert len(wal.recover())==1

def test_ws_archive_semantic_content_equivalence_and_microsecond_difference():
    ws=Trade('BTCUSDT',1735689600000,Decimal('1.0'),Decimal('0.10'),'Buy','one')
    archive=Trade('BTCUSDT',1735689600000,Decimal('1'),Decimal('0.1'),'Buy','one',ts_us=1735689600000000)
    precise=Trade('BTCUSDT',1735689600000,Decimal('1'),Decimal('0.1'),'Buy','one',ts_us=1735689600000001)
    assert delivery_identity(ws)==delivery_identity(archive)
    assert delivery_identity(ws)['delivery_key']==delivery_identity(precise)['delivery_key']
    assert delivery_identity(ws)['content_sha256']!=delivery_identity(precise)['content_sha256']

@pytest.mark.asyncio
async def test_lost_wal_ack_replays_exact_transaction_without_duplicating(tmp_path,monkeypatch):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,_=owner(tmp_path,root,persistent)
    async def lose_ack(_):raise OSError('synthetic WAL acknowledgement lost')
    monkeypatch.setattr(wal,'ack',lose_ack)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT')
    before=copy.deepcopy(persistent);fresh,new_wal,_=owner(tmp_path,root,persistent)
    await fresh.ingest(locator,sha,size,'BTCUSDT')
    assert persistent==before and not new_wal.recover()

@pytest.mark.asyncio
async def test_skipped_checkpoint_offset_refused_without_events(tmp_path):
    from market_data.raw_capture import encode_observation
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,_=owner(tmp_path,root,persistent,fail_before=True)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT',batch_size=1)
    _,payload=wal.recover()[0];observation=payload['observation'];observation['archive'].update(start_row='1',end_row='2');observation['observation_index']='2'
    connection=Connection(persistent);store=CaptureStore(connection)
    with pytest.raises(ValueError):await store.store_archive_batch(observation_bytes=encode_observation(observation),events=payload['events'])
    assert persistent==state()

@pytest.mark.asyncio
async def test_mutated_wal_event_cannot_be_acknowledged(tmp_path):
    root,locator,sha,size=fixture(tmp_path);persistent=state();importer,wal,_=owner(tmp_path,root,persistent,fail_before=True)
    with pytest.raises(OSError):await importer.ingest(locator,sha,size,'BTCUSDT')
    rid,payload=wal.recover()[0];payload['events'][0]['price']='999'
    fresh,new_wal,_=owner(tmp_path,root,persistent)
    with pytest.raises(ValueError):await fresh._replay(rid,payload)
    assert persistent==state() and len(new_wal.recover())==1

def test_private_snapshot_stays_exact_when_original_path_changes(tmp_path):
    from market_data.archive_import import blob_snapshot
    root,locator,sha,size=fixture(tmp_path);original=(root/locator).read_bytes()
    with blob_snapshot(root,locator,sha,size) as private:
        (root/locator).write_bytes(b'replaced')
        assert private.read_bytes()==original
    assert not private.exists()

@pytest.mark.parametrize('locator',['../escape.csv.gz','/absolute.csv.gz','a\\b.csv.gz','a/../b.csv.gz','https://other/blob'])
def test_blob_locator_is_closed_logical_relative_path(tmp_path,locator):
    from market_data.archive_import import blob_snapshot
    with pytest.raises(ValueError):
        with blob_snapshot(tmp_path,locator,'a'*64,1):pass

def test_event_wire_is_exact_microsecond_text_not_js_or_f64_number():
    from market_data.public_trades import execution_record,decode_execution_record
    trade=Trade('BTCUSDT',253402300799999,Decimal('1.0'),Decimal('1e-1000'),'Buy','one',ts_us=253402300799999999)
    record=execution_record(trade)
    assert record['timestamp_us']=='253402300799999999' and type(record['timestamp_us']) is str
    assert decode_execution_record(record)==trade
    with pytest.raises(ValueError):Trade('BTCUSDT',2**53,Decimal(1),Decimal(1),'Buy','overflow')

@pytest.mark.asyncio
async def test_checkpoint_read_never_opens_uncommitted_implicit_outer_transaction(tmp_path):
    class ExplicitOnly(Connection):
        inside=False
        @asynccontextmanager
        async def transaction(self):
            assert not self.inside
            self.inside=True
            try:
                async with super().transaction():yield self
            finally:self.inside=False
        async def execute(self,sql,p=()):
            if not self.inside:raise AssertionError('implicit outer transaction would remain open')
            return await super().execute(sql,p)
    root,locator,sha,size=fixture(tmp_path);persistent=state();connection=ExplicitOnly(persistent)
    importer=ArchiveImporter(root,CaptureStore(connection),SegmentWAL(tmp_path/'wal'),source_revision='a'*40)
    await importer.ingest(locator,sha,size,'BTCUSDT')
    assert len(persistent['events'])==2 and not connection.inside

@pytest.mark.asyncio
async def test_checkpoint_write_refusal_cannot_return_commit_ack(tmp_path):
    class MissingCheckpoint(Connection):
        async def execute(self,sql,p=()):
            if 'archive:write_checkpoint' in sql:return self
            return await super().execute(sql,p)
    root,locator,sha,size=fixture(tmp_path);persistent=state();wal=SegmentWAL(tmp_path/'wal')
    importer=ArchiveImporter(root,CaptureStore(MissingCheckpoint(persistent)),wal,source_revision='a'*40)
    with pytest.raises(ValueError):await importer.ingest(locator,sha,size,'BTCUSDT')
    assert persistent==state() and len(wal.recover())==1

@pytest.mark.asyncio
async def test_constructor_and_existing_active_session_are_refused_without_repair(tmp_path):
    persistent=state();connection=Connection(persistent);connection.info.transaction_status=2
    with pytest.raises(ValueError):CaptureStore(connection)
    assert persistent==state() and not connection.closed
    connection.info.transaction_status=0;store=CaptureStore(connection);connection.info.transaction_status=2
    with pytest.raises(ValueError):await store.archive_checkpoint('a'*64)
    assert persistent==state() and not connection.closed and connection.info.transaction_status==2

@pytest.mark.asyncio
async def test_open_identity_and_session_lock_reads_own_explicit_outer_transaction(monkeypatch):
    import sys
    from types import SimpleNamespace
    class Opening(Connection):
        inside=False
        @asynccontextmanager
        async def transaction(self):
            assert not self.inside and self.info.transaction_status==0
            self.inside=True;self.info.transaction_status=2
            try:yield self
            finally:self.inside=False;self.info.transaction_status=0
        async def execute(self,sql,p=()):
            assert self.inside,'constructor read would create implicit outer transaction'
            self.pending=('fixture',) if 'current_database()' in sql else (True,)
            self.catalog_kind=next((kind for kind in ('relations','columns','keys','indexes') if 'prepared:'+kind in sql),None)
            return self
        async def fetchall(self):
            from test_capture_prepared_schema import prepared_rows
            return prepared_rows()[self.catalog_kind]
        async def commit(self):raise AssertionError('do not repair implicit caller transaction by committing it')
    connection=Opening(state())
    async def connect(*args,**kwargs):return connection
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect)))
    store=await CaptureStore.open('synthetic://not-a-real-db',expected_database='fixture')
    assert store._connection is connection and not connection.inside and connection.info.transaction_status==0

@pytest.mark.asyncio
async def test_unknown_ws_commit_poisoned_store_cannot_resume_with_same_session():
    from test_capture_store import Connection as WSConnection,recorder
    from test_capture_runtime import Sink
    connection=WSConnection(fail_commit=True);store=CaptureStore(connection)
    # Build valid v2 bytes using a recording sink, without any transport.
    sink=Sink();capture=recorder(sink);capture.begin_connection();await capture.frame(b'one')
    raw,payload=sink.rows[0]
    with pytest.raises(OSError):await store.store_capture(observation_bytes=raw,payload_bytes=payload)
    connection.fail_commit=False
    with pytest.raises(RuntimeError):await store.store_capture(observation_bytes=raw,payload_bytes=payload)
    assert connection.closed and connection.rows=={}

@pytest.mark.parametrize('status',[1,2,3,4,None,False])
def test_nonidle_or_unproven_session_never_adopted(status):
    connection=Connection(state());connection.info.transaction_status=status
    with pytest.raises(ValueError):CaptureStore(connection)
    assert not connection.closed

@pytest.mark.asyncio
@pytest.mark.parametrize('when',['sql','lock'])
async def test_validated_batch_snapshot_survives_caller_mutation(tmp_path,when):
    import asyncio
    from market_data.archive_import import batch_observation,import_identity
    from market_data.public_trades import execution_record,digest_json
    events=[execution_record(Trade('BTCUSDT',1,'1','1','Buy','one'))]
    archive=dict(import_id=import_identity('a'*64,'BTCUSDT'),blob_sha256='a'*64,blob_bytes='1',locator='x.csv.gz',format='BYBIT_CSV_GZIP',rows='1',start_row='0',end_row='1',events_sha256=digest_json(events),source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN')
    raw=batch_observation(archive,'BTCUSDT','b'*40,None)
    class Mutating(Connection):
        mutated=False
        async def execute(self,sql,p=()):
            if when=='sql' and not self.mutated:self.mutated=True;events[0]['price']='999'
            return await super().execute(sql,p)
    persistent=state();store=CaptureStore(Mutating(persistent))
    if when=='lock':await store._lock.acquire()
    task=asyncio.create_task(store.store_archive_batch(observation_bytes=raw,events=events))
    if when=='lock':
        await asyncio.sleep(0);events[0]['price']='999';events.append(dict(events[0]));store._lock.release()
    receipt=await task
    assert receipt['committed'] is True and next(iter(persistent['events'].values()))[2]=='1'

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['fresh','replay'])
@pytest.mark.parametrize('bad',[None,{}, {'committed':False},{'committed':1}, {'committed':True,'import_id':'bad'}])
async def test_unconfirmed_store_ack_retains_wal_and_poisoned_owner(tmp_path,mode,bad):
    root,locator,sha,size=fixture(tmp_path);wal=SegmentWAL(tmp_path/'wal')
    class Unconfirmed:
        async def archive_checkpoint(self,_):return None
        async def store_archive_batch(self,**kwargs):return bad
    importer=ArchiveImporter(root,Unconfirmed(),wal,source_revision='a'*40)
    with pytest.raises(ValueError):await importer.ingest(locator,sha,size,'BTCUSDT')
    assert importer.failed and len(wal.recover())==1
    if mode=='replay':
        fresh=ArchiveImporter(root,Unconfirmed(),SegmentWAL(tmp_path/'wal'),source_revision='a'*40)
        with pytest.raises(ValueError):await fresh.recover()
        assert fresh.failed and len(wal.recover())==1

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['fresh','replay'])
@pytest.mark.parametrize('change',[{'import_id':'0'*64},{'committed_source_rows':True},{'committed_source_rows':999},{'observation_sha256':'0'*64},{'committed':1},{'source_authenticity':'VERIFIED'},{'point_in_time_availability':'KNOWN'},{'native_authority_verified':True}])
async def test_every_commit_receipt_binding_is_required_before_wal_ack(tmp_path,mode,change):
    from market_data.raw_capture import decode_observation
    root,locator,sha,size=fixture(tmp_path);wal=SegmentWAL(tmp_path/'wal')
    class WrongBinding:
        async def archive_checkpoint(self,_):return None
        async def store_archive_batch(self,*,observation_bytes,events):
            archive=decode_observation(observation_bytes)['archive']
            expected=dict(import_id=archive['import_id'],committed_source_rows=int(archive['end_row']),observation_sha256=hashlib.sha256(observation_bytes).hexdigest(),committed=True,source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN',native_authority_verified=False)
            return dict(expected,**change)
    importer=ArchiveImporter(root,WrongBinding(),wal,source_revision='a'*40)
    with pytest.raises(ValueError):await importer.ingest(locator,sha,size,'BTCUSDT')
    assert importer.failed and len(wal.recover())==1
    if mode=='replay':
        fresh=ArchiveImporter(root,WrongBinding(),SegmentWAL(tmp_path/'wal'),source_revision='a'*40)
        with pytest.raises(ValueError):await fresh.recover()
        assert fresh.failed and len(wal.recover())==1

@pytest.mark.asyncio
@pytest.mark.parametrize('oversize',['batch','record','value'])
async def test_invalid_archive_input_refuses_before_unbounded_snapshot_or_hash(tmp_path,oversize):
    import tracemalloc
    from market_data.archive_import import batch_observation,import_identity
    from market_data.public_trades import execution_record,digest_json
    valid=execution_record(Trade('BTCUSDT',1,'1','1','Buy','one'))
    archive=dict(import_id=import_identity('a'*64,'BTCUSDT'),blob_sha256='a'*64,blob_bytes='1',locator='x.csv.gz',format='BYBIT_CSV_GZIP',rows='1',start_row='0',end_row='1',events_sha256=digest_json([valid]),source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN')
    raw=batch_observation(archive,'BTCUSDT','b'*40,None)
    events=[valid]*100000 if oversize=='batch' else [dict(valid)]
    if oversize=='record':events[0].update({str(i):'x' for i in range(50000)})
    if oversize=='value':events[0]['price']='1'*1000000
    persistent=state();store=CaptureStore(Connection(persistent))
    tracemalloc.start()
    try:
        with pytest.raises(ValueError):await store.store_archive_batch(observation_bytes=raw,events=events)
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert peak<262144,'invalid input must refuse before proportional copy/hash allocation'
    assert persistent==state()
