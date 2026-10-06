"""Import Strattester historical scientific bootstrap without promoting it to live evidence."""
from __future__ import annotations
import hashlib,json,uuid

REQUIRED_CAPABILITIES=("candles","open_interest","public_trade_aggregates")
FORBIDDEN_AS_HISTORICAL=("true_l2_orderbook","liquidations","true_l2_absorption")

def canonical_payload(bundle):
    x={k:v for k,v in dict(bundle).items() if k!="sha256"}
    return json.dumps(x,sort_keys=True,separators=(",",":"),default=str)

def verify_bundle(bundle):
    b=dict(bundle or {})
    expected=str(b.get("sha256") or "")
    actual=hashlib.sha256(canonical_payload(b).encode()).hexdigest()
    if expected!=actual:return False,"sha256 mismatch"
    if str(b.get("research_scope"))!="HISTORICAL_BOOTSTRAP_ONLY":
        return False,"invalid research scope"
    caps=dict(b.get("capabilities") or {})
    if not all(bool(caps.get(k)) for k in REQUIRED_CAPABILITIES):
        return False,"required historical capability missing"
    if any(bool(caps.get(k)) for k in FORBIDDEN_AS_HISTORICAL):
        return False,"fabricated historical live-only capability"
    return True,None

async def import_historical_science(pool,bundle):
    ok,reason=verify_bundle(bundle)
    if not ok:raise ValueError(reason)
    bid=uuid.uuid4();caps=dict(bundle.get("capabilities") or {})
    row=await pool.fetchrow("""INSERT INTO historical_scientific_bundles(
      id,source,sha256,capabilities,research_scope,created_at_source,details)
      VALUES($1,$2,$3,$4::jsonb,$5,$6,$7::jsonb)
      ON CONFLICT(sha256) DO UPDATE SET details=EXCLUDED.details
      RETURNING id,status""",
      bid,str(bundle.get("source") or "strattester"),str(bundle["sha256"]),
      json.dumps(caps,sort_keys=True,separators=(",",":")),
      str(bundle["research_scope"]),float(bundle.get("created_at") or 0),
      json.dumps({"schema":bundle.get("schema",1)},separators=(",",":")))
    bundle_id=row["id"]
    for item in bundle.get("symbols") or ():
        features=dict(item.get("features") or {})
        scalp_events=list(features.get("scalp_events") or ())
        features["scalp_events"]=scalp_events[-2048:]
        await pool.execute("""INSERT INTO historical_scientific_symbol_state(
          bundle_id,symbol,status,samples,from_ms,through_ms,summary,features)
          VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb)
          ON CONFLICT(bundle_id,symbol) DO UPDATE SET status=EXCLUDED.status,
          samples=EXCLUDED.samples,from_ms=EXCLUDED.from_ms,through_ms=EXCLUDED.through_ms,
          summary=EXCLUDED.summary,features=EXCLUDED.features""",
          bundle_id,str(item.get("symbol") or ""),str(item.get("status") or "UNKNOWN"),
          int(item.get("samples") or 0),item.get("from_ms"),item.get("through_ms"),
          json.dumps(item.get("summary") or {},sort_keys=True,separators=(",",":")),
          json.dumps(item.get("features") or {},sort_keys=True,separators=(",",":")))
    scalp_count=sum(len(((x.get("features") or {}).get("scalp_events") or ())) for x in bundle.get("symbols") or ())
    return {"bundle_id":str(bundle_id),"status":row["status"],"symbols":len(bundle.get("symbols") or ()),
            "historical_scalp_events":scalp_count,"live_evidence_promoted":False}
