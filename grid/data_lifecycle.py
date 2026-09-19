from datetime import datetime,timezone

DERIVED_DISPOSABLE={
 "market_features_1m","shadow_predictions","strategy_results"
}

def useless_derived(status,eligible,has_dependents=False):
    """Only derived rows may be early-GC candidates; authoritative market data never are."""
    if has_dependents:return False
    return status in ("INSUFFICIENT","CORRUPT","ORPHANED") or eligible is False

async def protected_sample_ids(pool):
    rows=await pool.fetch("""SELECT DISTINCT ds.sample_id FROM dataset_samples ds
      JOIN dataset_snapshots d ON d.id=ds.dataset_id
      WHERE d.status IN ('BUILDING','READY')
      UNION
      SELECT DISTINCT ds.sample_id FROM dataset_samples ds
      JOIN model_registry m ON m.dataset_id=ds.dataset_id
      WHERE m.status NOT IN ('REJECTED','RETIRED')""")
    return {r["sample_id"] for r in rows}
