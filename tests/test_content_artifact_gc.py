import asyncio
from grid.ml_artifact_gc import delete_unreferenced_content_artifacts


class Pool:
    def __init__(self,rows,active_same=0):
        self.rows=rows;self.active_same=active_same;self.calls=[]
    async def fetch(self,sql,*args):
        return self.rows
    async def execute(self,sql,*args):
        self.calls.append((sql,args));return "UPDATE 1"
    async def fetchval(self,sql,*args):
        return self.active_same


class Cache:
    def __init__(self):self.discarded=[]
    def discard(self,digest):
        self.discarded.append(digest);return True


def test_unreferenced_content_artifact_removes_cache_object():
    row={"id":"a1","storage_uri":"content://sha256/"+"a"*64}
    async def run():
        p=Pool([row],0);cache=Cache()
        assert await delete_unreferenced_content_artifacts(p,cache,30,10)==1
        assert cache.discarded==["a"*64]
        assert any("status='DELETED'" in sql for sql,_ in p.calls)
    asyncio.run(run())


def test_shared_active_content_is_not_removed():
    row={"id":"a1","storage_uri":"content://sha256/"+"b"*64}
    async def run():
        p=Pool([row],1);cache=Cache()
        assert await delete_unreferenced_content_artifacts(p,cache,30,10)==1
        assert cache.discarded==[]
    asyncio.run(run())
