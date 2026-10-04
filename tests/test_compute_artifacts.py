import asyncio
from grid.compute_artifacts import publish_compute_artifact,compute_artifact_descriptor
from grid.config import settings


class Pool:
    def __init__(self):
        self.row=None
    async def fetchrow(self,sql,*args):
        if "storage_uri" in sql:
            return self.row
        if "WHERE id=$1" in sql:
            return self.row
        return None
    async def execute(self,sql,*args):
        if sql.lstrip().startswith("INSERT INTO ml_artifacts"):
            self.row={"id":args[0],"artifact_type":args[1],"storage_uri":args[2],
                      "bytes":args[3],"status":"ACTIVE","reusable":args[4],"metadata":{}}
            return "INSERT 0 1"
        return "UPDATE 1"


def test_publish_and_describe_compute_artifact(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"content_cache_root",str(tmp_path/"cache"))
    source=tmp_path/"dataset.db";source.write_bytes(b"immutable")
    async def run():
        p=Pool()
        published=await publish_compute_artifact(p,source)
        assert published["dataset_sha256"] if "dataset_sha256" in published else published["sha256"]
        desc=await compute_artifact_descriptor(p,p.row["id"])
        assert len(desc["dataset_sha256"])==64
        assert desc["bytes"]==len(b"immutable")
    asyncio.run(run())
