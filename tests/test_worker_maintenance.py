from pathlib import Path
import os,time
from grid.content_cache import ContentAddressedCache
from grid.worker_maintenance import cleanup_stale_workspaces


def test_cache_gc_enforces_budget(tmp_path):
    cache=ContentAddressedCache(tmp_path/"cache")
    a=tmp_path/"a";a.write_bytes(b"a"*100)
    b=tmp_path/"b";b.write_bytes(b"b"*100)
    x=cache.put(a);y=cache.put(b)
    old=time.time()-1000
    os.utime(x["path"],(old,old));os.utime(y["path"],(old,old))
    result=cache.gc(100,10)
    assert result["bytes_remaining"]<=100


def test_workspace_cleanup_only_deletes_owned_prefixes(tmp_path):
    owned=tmp_path/"grid-strattester-old";owned.mkdir()
    foreign=tmp_path/"other-old";foreign.mkdir()
    old=time.time()-1000
    os.utime(owned,(old,old));os.utime(foreign,(old,old))
    cleanup_stale_workspaces(tmp_path,10)
    assert not owned.exists()
    assert foreign.exists()


def test_cache_gc_does_not_delete_protected_digest(tmp_path):
    cache=ContentAddressedCache(tmp_path/"cache")
    source=tmp_path/"protected";source.write_bytes(b"keep")
    item=cache.put(source)
    old=time.time()-1000;os.utime(item["path"],(old,old))
    result=cache.gc(0,1,protected=[item["sha256"]])
    assert Path(item["path"]).exists()
    assert result["deleted"]==0
