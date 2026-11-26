"""Receipt/cache claims and limits; fake transport/native-lock backend only."""
import json
from datetime import date
import pytest
from market_data import archive_ingestion
from market_data.archive_file_lock import archive_file_lock,async_archive_file_lock
from test_archive_ingestion import make_gzip,URL

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('rows',2),('first_ms',1735689600001),('last_ms',1735689600001)])
async def test_tampered_positive_receipt_metadata_cannot_skip_content_audit(tmp_path,monkeypatch,field,value):
    path=tmp_path/'archive.csv.gz';calls=[]
    async def fake(session,url,dest,**kw):calls.append(1);make_gzip(dest);return dest
    monkeypatch.setattr(archive_ingestion,'download_archive',fake)
    original=await archive_ingestion.acquire_archive(None,URL,path)
    receipt=path.with_name(path.name+'.audit.json');data=json.loads(receipt.read_text());data[field]=value;receipt.write_text(json.dumps(data))
    observed=await archive_ingestion.acquire_archive(None,URL,path)
    assert observed==original and len(calls)==2

@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),-1,121])
def test_invalid_lock_budget_refuses_before_filesystem_effects(tmp_path,bad):
    target=tmp_path/'never-created'/'archive.csv.gz'
    with pytest.raises(ValueError):
        with archive_file_lock(target,timeout=bad):pass
    assert not target.parent.exists()

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),-1,121])
async def test_invalid_async_lock_budget_refuses_before_effects(tmp_path,bad):
    target=tmp_path/'never-created'/'archive.csv.gz'
    with pytest.raises(ValueError):
        async with async_archive_file_lock(target,timeout=bad):pass
    assert not target.parent.exists()

@pytest.mark.asyncio
async def test_batch_limits_refuse_before_session_construction(monkeypatch):
    import aiohttp
    def deny(*args,**kw):raise AssertionError('NO_TRANSPORT_CONSTRUCTION')
    monkeypatch.setattr(aiohttp,'ClientSession',deny)
    for changes in ({'concurrency':65},{'max_bytes':2_000_000_001}):
        with pytest.raises(ValueError):await archive_ingestion.acquire_many([],**changes)

@pytest.mark.asyncio
async def test_related_link_refused_before_any_transport_or_mutation(tmp_path,monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    from market_data.bybit_archive_download import download_archive
    target=tmp_path/'never-created'/'archive.csv.gz';partial=target.with_name(target.name+'.partial');original=Path.lstat
    def facts(path,*args,**kwargs):
        if path==partial:return SimpleNamespace(st_mode=stat.S_IFLNK,st_nlink=1,st_file_attributes=0)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',facts)
    class Denied:
        def get(self,*args,**kwargs):raise AssertionError('NO_TRANSPORT')
    with pytest.raises(ValueError):await download_archive(Denied(),URL,target)
    assert not target.parent.exists()

def test_cached_receipt_metadata_has_read_byte_budget(tmp_path):
    path=tmp_path/'archive.csv.gz';make_gzip(path)
    sidecar=path.with_name(path.name+'.audit.json');sidecar.write_bytes(b' '*16385)
    class DeniedRead:
        pass
    assert archive_ingestion._load_receipt(path,URL) is None
