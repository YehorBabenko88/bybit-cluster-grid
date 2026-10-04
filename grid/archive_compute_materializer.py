from __future__ import annotations
from datetime import datetime
from .archive_compaction import CompactionEvidence,record_compaction
from .archive_derived_artifact import iter_derived_artifact,inspect_derived_artifact,FORMAT
from .archive_materializer import materialize_archive_stream
from .content_cache import ContentAddressedCache
from .data_capabilities import set_capability


def _parse_ts(value):
    if value is None:return None
    if isinstance(value,datetime):return value
    return datetime.fromisoformat(str(value).replace("Z","+00:00"))


async def materialize_archive_compute_results(pool,cache_root,limit=10):
    rows=await pool.fetch("""SELECT j.*,a.storage_uri,a.status AS artifact_status,a.bytes AS artifact_bytes
      FROM archive_compute_jobs j JOIN ml_artifacts a ON a.id=j.derived_artifact_id
      WHERE j.status='done' AND j.materialized_at IS NULL
      ORDER BY j.updated_at,j.archive_date,j.symbol LIMIT $1""",int(limit))
    completed=0
    cache=ContentAddressedCache(cache_root)
    prefix="content://sha256/"
    for job in rows:
        try:
            manifest=dict(job["result_manifest"] or {})
            if job["artifact_status"]!="ACTIVE":
                raise ValueError("archive derived artifact is not active")
            uri=str(job["storage_uri"] or "")
            if not uri.startswith(prefix):
                raise ValueError("archive derived artifact is not content-addressed")
            sha=uri[len(prefix):]
            if sha!=str(manifest.get("derived_artifact_sha256") or "").lower():
                raise ValueError("archive materialization artifact hash mismatch")
            if int(job["artifact_bytes"] or 0)!=int(manifest.get("derived_artifact_bytes",-1)):
                raise ValueError("archive materialization artifact byte size mismatch")
            if not cache.has(sha):
                raise FileNotFoundError("archive derived artifact missing from CONTROL cache")
            expected_meta={"symbol":job["symbol"],"archive_date":str(job["archive_date"]),
                           "tick_size":float(job["tick_size"]),
                           "source_sha256":manifest.get("source_sha256")}
            artifact_path=cache.path_for(sha)
            inspected=inspect_derived_artifact(artifact_path,expected_meta)
            for key in ("source_rows","derived_candles","derived_footprint_rows"):
                if int(inspected[key])!=int(manifest.get(key,-1)):
                    raise ValueError(f"archive artifact {key} mismatch")
            expected_min=_parse_ts(manifest.get("min_ts"));expected_max=_parse_ts(manifest.get("max_ts"))
            if inspected["min_ts"]!=expected_min or inspected["max_ts"]!=expected_max:
                raise ValueError("archive artifact time range mismatch")
            derived=await materialize_archive_stream(
                pool,iter_derived_artifact(artifact_path,expected_meta),batch_minutes=30)
            for key in ("source_rows","derived_candles","derived_footprint_rows"):
                if int(derived[key])!=int(inspected[key]):
                    raise ValueError(f"archive materialization {key} mismatch")
            if derived["min_ts"]!=inspected["min_ts"] or derived["max_ts"]!=inspected["max_ts"]:
                raise ValueError("archive materialization time range mismatch")
            evidence=CompactionEvidence(
                derived["source_rows"],derived["derived_candles"],
                derived["derived_footprint_rows"],derived["min_ts"],derived["max_ts"])
            await record_compaction(pool,job["symbol"],job["archive_date"],
                manifest["source_sha256"],evidence,
                {"distributed":True,"derived_format":manifest.get("derived_format",FORMAT),
                 "artifact_sha256":sha,"artifact_id":str(job["derived_artifact_id"])})
            await pool.execute("""UPDATE trade_archive_backfill SET status='done',rows=$3,sha256=$4,
              updated_at=now(),last_error=NULL WHERE symbol=$1 AND archive_date=$2""",
              job["symbol"],job["archive_date"],derived["source_rows"],manifest["source_sha256"])
            await set_capability(pool,job["symbol"],"trade_history","PARTIAL")
            await set_capability(pool,job["symbol"],"footprint_history","PARTIAL")
            await pool.execute("""UPDATE archive_compute_jobs SET materialized_at=now(),
              materialize_error=NULL,updated_at=now() WHERE id=$1 AND materialized_at IS NULL""",job["id"])
            completed+=1
        except Exception as exc:
            await pool.execute("""UPDATE archive_compute_jobs SET materialize_error=$2,updated_at=now()
              WHERE id=$1 AND materialized_at IS NULL""",job["id"],str(exc)[:4000])
    return completed
