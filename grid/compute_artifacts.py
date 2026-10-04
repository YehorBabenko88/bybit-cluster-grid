from __future__ import annotations
import json,os,tempfile,uuid
from pathlib import Path
from .config import settings
from .content_cache import ContentAddressedCache


async def publish_compute_artifact(pool,path,artifact_type="research_dataset",metadata=None,reusable=True):
    """Publish a verified immutable file into CONTROL content cache and artifact registry."""
    cache=ContentAddressedCache(settings.content_cache_root)
    item=cache.put(Path(path))
    uri=f"content://sha256/{item['sha256']}"
    existing=await pool.fetchrow("""SELECT * FROM ml_artifacts
      WHERE storage_uri=$1 AND status='ACTIVE' ORDER BY created_at LIMIT 1""",uri)
    if existing:
        await pool.execute("UPDATE ml_artifacts SET last_used_at=now() WHERE id=$1",existing["id"])
        row=dict(existing)
        row["sha256"]=item["sha256"]
        return row
    artifact_id=uuid.uuid4()
    await pool.execute("""INSERT INTO ml_artifacts
      (id,artifact_type,storage_uri,bytes,status,reusable,metadata)
      VALUES($1,$2,$3,$4,'ACTIVE',$5,$6::jsonb)""",
      artifact_id,str(artifact_type),uri,int(item["bytes"]),bool(reusable),json.dumps(metadata or {}))
    return {"id":str(artifact_id),"artifact_type":str(artifact_type),"storage_uri":uri,
            "bytes":int(item["bytes"]),"sha256":item["sha256"],"reusable":bool(reusable)}


async def compute_artifact_descriptor(pool,artifact_id):
    row=await pool.fetchrow("""SELECT * FROM ml_artifacts
      WHERE id=$1 AND status='ACTIVE'""",artifact_id)
    if not row:raise ValueError("active compute artifact not found")
    uri=str(row["storage_uri"])
    prefix="content://sha256/"
    if not uri.startswith(prefix):raise ValueError("artifact is not content-addressed")
    sha=uri[len(prefix):]
    if len(sha)!=64:raise ValueError("invalid content artifact digest")
    await pool.execute("UPDATE ml_artifacts SET last_used_at=now() WHERE id=$1",artifact_id)
    return {"artifact_id":str(row["id"]),"dataset_sha256":sha,"bytes":int(row["bytes"] or 0)}


async def publish_compute_bytes(pool,data,artifact_type="research_result",metadata=None,reusable=True):
    raw=data if isinstance(data,(bytes,bytearray)) else bytes(data)
    cache_root=Path(settings.content_cache_root)
    cache_root.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="grid-artifact-",suffix=".tmp",dir=cache_root);os.close(fd)
    try:
        with open(tmp,"wb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        return await publish_compute_artifact(pool,tmp,artifact_type=artifact_type,
            metadata=metadata,reusable=reusable)
    finally:
        try:os.remove(tmp)
        except FileNotFoundError:pass
