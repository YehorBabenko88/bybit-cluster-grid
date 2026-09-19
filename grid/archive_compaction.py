from dataclasses import dataclass

@dataclass(frozen=True)
class CompactionEvidence:
    source_rows:int
    derived_candles:int
    derived_footprint_rows:int
    min_ts:object
    max_ts:object

def safe_to_delete_raw(e):
    if not e:return False
    if int(e.source_rows)<=0 or int(e.derived_candles)<=0 or int(e.derived_footprint_rows)<=0:return False
    if e.min_ts is None or e.max_ts is None or e.min_ts>e.max_ts:return False
    # A day cannot have more than 1440 one-minute candles; zero coverage is never accepted.
    if int(e.derived_candles)>1440:return False
    return True

async def record_compaction(pool,symbol,archive_date,source_sha256,evidence,details=None):
    import json
    if not safe_to_delete_raw(evidence):raise ValueError("derived archive evidence incomplete; raw deletion blocked")
    await pool.execute("""INSERT INTO archive_compaction_manifests
      (symbol,archive_date,source_sha256,source_rows,derived_candles,derived_footprint_rows,min_ts,max_ts,status,verified_at,details)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,'VERIFIED',now(),$9::jsonb)
      ON CONFLICT(symbol,archive_date) DO UPDATE SET source_sha256=EXCLUDED.source_sha256,
      source_rows=EXCLUDED.source_rows,derived_candles=EXCLUDED.derived_candles,
      derived_footprint_rows=EXCLUDED.derived_footprint_rows,min_ts=EXCLUDED.min_ts,max_ts=EXCLUDED.max_ts,
      status='VERIFIED',verified_at=now(),details=EXCLUDED.details""",
      symbol,archive_date,source_sha256,evidence.source_rows,evidence.derived_candles,
      evidence.derived_footprint_rows,evidence.min_ts,evidence.max_ts,json.dumps(details or {}))

async def mark_raw_deleted(pool,symbol,archive_date):
    r=await pool.execute("""UPDATE archive_compaction_manifests SET status='COMPACTED',
      raw_deleted_at=now() WHERE symbol=$1 AND archive_date=$2 AND status='VERIFIED'""",symbol,archive_date)
    if not r.endswith(" 1"):raise RuntimeError("raw deletion not authorized by VERIFIED manifest")
