"""Canonical exact archive batches: durable blob references, WAL, one writer.

No second database Store or caller-provided historical completeness authority.
"""
import csv,gzip,hashlib,json,os,re,tempfile,time,uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from market_math import decimal_epoch_units
from .archive_file_lock import guard_archive_destination
from .bybit_archive_audit import audit_trade_gzip
from .public_trades import Trade,execution_record,decode_execution_record,digest_json
from .raw_capture import encode_observation,decode_observation

def _blob(root,locator,sha,size):
    if (type(locator) is not str or len(locator)>256
            or re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',locator) is None
            or any(part in ('.','..') for part in locator.split('/'))
            or type(sha) is not str or re.fullmatch('[a-f0-9]{64}',sha) is None
            or type(size) is not int or not 0<size<=2_000_000_000):
        raise ValueError('invalid archive blob reference')
    target=guard_archive_destination(Path(root)/locator)
    if not target.is_relative_to(Path(os.path.abspath(root))):raise ValueError('archive root escape')
    return target

@contextmanager
def blob_snapshot(root,locator,sha,size):
    source=_blob(root,locator,sha,size)
    with tempfile.TemporaryDirectory(prefix='market-data-archive-') as temporary:
        snapshot=Path(temporary)/'blob.csv.gz';digest=hashlib.sha256();count=0
        with source.open('rb') as reader,snapshot.open('wb') as writer:
            while True:
                block=reader.read(min(1<<20,size-count+1))
                if not block:break
                count+=len(block)
                if count>size:raise ValueError('archive blob size drift')
                writer.write(block);digest.update(block)
            writer.flush();os.fsync(writer.fileno())
        if count!=size or digest.hexdigest()!=sha:raise ValueError('archive blob hash drift')
        yield snapshot

def parse_archive_events(snapshot,symbol):
    with gzip.open(snapshot,'rt',encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle,strict=True)
        for row in reader:
            if 'symbol' in row and row['symbol']!=symbol:raise ValueError('archive symbol mismatch')
            microseconds=decimal_epoch_units(row['timestamp'],6)
            yield execution_record(Trade(symbol,microseconds//1000,row['price'],row['size'],row['side'],row['trdMatchID'],ts_us=microseconds))

def import_identity(sha,symbol):
    return digest_json(dict(schema='market_data.archive-import.v1',blob_sha256=sha,symbol=symbol,format='BYBIT_CSV_GZIP'))

def batch_observation(archive,symbol,revision,previous):
    return encode_observation(dict(schema='market_data.raw-capture-observation.v2',
        instrument=dict(exchange='bybit',category='linear',symbol=symbol,instrument_version='1'),
        producer_source_revision=revision,source_kind='ARCHIVE',endpoint='archive://bybit/linear',
        connection_id=str(uuid.UUID(archive['import_id'][:32],version=4)),
        observation_index=archive['end_row'],kind='archive_batch',
        received_at_utc=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),
        received_monotonic_ns=str(time.monotonic_ns()),payload_kind='EXTERNAL_BLOB',payload_sha256=None,payload_bytes='0',
        frame_metadata_sha256=None,previous_metadata_sha256=previous,exchange_event_at_utc=None,sequence=None,update_id=None,
        reason=None,publication='LOCAL_UNATTESTED',archive=archive))

class ArchiveImporter:
    def __init__(self,root,store,wal,*,source_revision):
        if type(source_revision) is not str or re.fullmatch('[a-f0-9]{40}',source_revision) is None:raise ValueError('exact source revision required')
        self.root=Path(root);self.store=store;self.wal=wal;self.revision=source_revision;self.failed=False;self.busy=False
    @staticmethod
    def _require_commit(result,raw):
        archive=decode_observation(raw)['archive']
        expected=dict(import_id=archive['import_id'],committed_source_rows=int(archive['end_row']),
            observation_sha256=hashlib.sha256(raw).hexdigest(),committed=True,
            source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN',native_authority_verified=False)
        if (type(result) is not dict or set(result)!=set(expected)
                or any(type(result[key]) is not type(value) or result[key]!=value for key,value in expected.items())):
            raise ValueError('ARCHIVE_COMMIT_OUTCOME_UNCONFIRMED')

    async def _replay(self,rid,payload):
        if type(payload) is not dict or set(payload)!={'schema','observation','events'} or payload['schema']!='market_data.archive-wal.v1':raise ValueError('foreign or invalid WAL payload')
        raw=encode_observation(payload['observation']);observation=decode_observation(raw);archive=observation['archive']
        if observation['source_kind']!='ARCHIVE':raise ValueError('archive WAL source mismatch')
        with blob_snapshot(self.root,archive['locator'],archive['blob_sha256'],int(archive['blob_bytes'])) as snapshot:
            audit=audit_trade_gzip(snapshot)
            if not audit.valid or audit.rows!=int(archive['rows']):raise ValueError('archive audit drift')
            start,end=int(archive['start_row']),int(archive['end_row']);events=[]
            for index,event in enumerate(parse_archive_events(snapshot,observation['instrument']['symbol'])):
                if start<=index<end:events.append(event)
                if index+1>=end:break
            if events!=payload['events'] or digest_json(events)!=archive['events_sha256']:raise ValueError('archive WAL content drift')
            result=await self.store.store_archive_batch(observation_bytes=raw,events=events)
            self._require_commit(result,raw)
            await self.wal.ack(rid)
            return result
    async def recover(self):
        if self.failed or self.busy:raise ValueError('archive owner requires fresh recovery')
        self.busy=True
        try:
            for rid,payload in self.wal.iter_recover():await self._replay(rid,payload)
        except BaseException:self.failed=True;raise
        finally:self.busy=False
    async def ingest(self,locator,sha,size,symbol,*,batch_size=1024):
        if type(batch_size) is not int or not 1<=batch_size<=1024:raise ValueError('bounded archive batch required')
        if type(symbol) is not str or re.fullmatch('[A-Z0-9]{2,30}',symbol) is None:raise ValueError('invalid archive instrument')
        await self.recover();self.busy=True
        try:
            with blob_snapshot(self.root,locator,sha,size) as snapshot:
                audit=audit_trade_gzip(snapshot)
                if not audit.valid:raise ValueError('archive content audit refused')
                if sum(1 for _ in parse_archive_events(snapshot,symbol))!=audit.rows:raise ValueError('archive adapter row count mismatch')
                identity=import_identity(sha,symbol);checkpoint=await self.store.archive_checkpoint(identity)
                start=0 if checkpoint is None else checkpoint['committed_rows']
                previous=None if checkpoint is None else checkpoint['last_observation_sha256']
                if checkpoint is not None and (checkpoint['blob_sha256']!=sha or checkpoint['total_rows']!=audit.rows or not 0<=start<=audit.rows):raise ValueError('archive checkpoint source mismatch')
                batch=[]
                for index,event in enumerate(parse_archive_events(snapshot,symbol),1):
                    if index<=start:continue
                    batch.append(event)
                    if len(batch)==batch_size or index==audit.rows:
                        archive=dict(import_id=identity,blob_sha256=sha,blob_bytes=str(size),locator=locator,format='BYBIT_CSV_GZIP',
                            rows=str(audit.rows),start_row=str(start),end_row=str(index),events_sha256=digest_json(batch),
                            source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN')
                        raw=batch_observation(archive,symbol,self.revision,previous)
                        payload=dict(schema='market_data.archive-wal.v1',observation=decode_observation(raw),events=batch)
                        if len(json.dumps(payload,separators=(',',':')).encode())>1048576:raise ValueError('archive batch WAL byte budget')
                        rid=await self.wal.append(payload)
                        result=await self.store.store_archive_batch(observation_bytes=raw,events=batch)
                        self._require_commit(result,raw)
                        await self.wal.ack(rid)
                        start=index;previous=hashlib.sha256(raw).hexdigest();batch=[]
                return dict(schema='market_data.archive-import.receipt.v1',import_id=identity,committed_source_rows=start,
                    source_authenticity='UNKNOWN',point_in_time_availability='UNKNOWN',coverage='UNKNOWN',execution_authority=False)
        except BaseException:self.failed=True;raise
        finally:self.busy=False
