import os
from .archive_disk_budget import archive_allowed
from .archive_download import download_verified,safe_delete_owned
from .archive_stream_parser import iter_minute_aggregates
from .archive_materializer import materialize_archive
from .archive_compaction import CompactionEvidence,record_compaction,mark_raw_deleted
from .data_capabilities import set_capability

async def process_archive(pool,job,archive_root,tick_size):
    ok,why=archive_allowed(archive_root,job.get("bytes"))
    if not ok:raise RuntimeError("archive disk guard: "+why["reason"])
    dl=await download_verified(job["source_uri"],archive_root,job.get("sha256"),job.get("bytes"))
    path=dl["path"]
    try:
        aggregates=list(iter_minute_aggregates(path,job["symbol"],tick_size))
        # Bounded by one archive/day; raw trades are never retained in this list.
        derived=await materialize_archive(pool,aggregates)
        source_rows=sum(int(x["trade_count"]) for x in aggregates)
        ev=CompactionEvidence(source_rows,derived["derived_candles"],derived["derived_footprint_rows"],
                              derived["min_ts"],derived["max_ts"])
        await record_compaction(pool,job["symbol"],job["archive_date"],dl["sha256"],ev,
                                {"download_bytes":dl["bytes"]})
        safe_delete_owned(path,archive_root)
        await mark_raw_deleted(pool,job["symbol"],job["archive_date"])
        await pool.execute("""UPDATE trade_archive_backfill SET status='done',rows=$3,sha256=$4,
          updated_at=now(),last_error=NULL WHERE symbol=$1 AND archive_date=$2""",
          job["symbol"],job["archive_date"],source_rows,dl["sha256"])
        await set_capability(pool,job["symbol"],"trade_history","PARTIAL")
        await set_capability(pool,job["symbol"],"footprint_history","PARTIAL")
        return {"symbol":job["symbol"],"date":str(job["archive_date"]),**derived,"source_rows":source_rows}
    except BaseException:
        # Keep a successfully downloaded raw file after processing failure for diagnosis/retry.
        raise
