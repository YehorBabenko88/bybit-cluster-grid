"""Persistent scientific memory for hypotheses and independent evidence."""
from __future__ import annotations
import json, uuid
from .scientific_hypotheses import Evidence,HypothesisSpec,evidence_passes,lifecycle

async def register_hypothesis(pool,spec:HypothesisSpec):
    fp=spec.fingerprint()
    definition=json.dumps(spec.canonical(),sort_keys=True,separators=(",",":"))
    row=await pool.fetchrow("""INSERT INTO scientific_hypotheses(
      id,fingerprint,method,pattern,horizon_ms,direction,feature_version,definition,status,research_only)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,'CANDIDATE',true)
      ON CONFLICT(fingerprint) DO UPDATE SET updated_at=now()
      RETURNING id,fingerprint,status""",
      uuid.uuid4(),fp,spec.method,spec.pattern,int(spec.horizon_ms),int(spec.direction),
      spec.feature_version,definition)
    return dict(row)

async def _load_evidence(pool,hypothesis_id):
    hypothesis_id=uuid.UUID(str(hypothesis_id))
    rows=await pool.fetch("""SELECT experiment_key,symbol,regime,split_key,sample_count,
      mean_return_bps,hit_rate,cost_bps,dataset_cutoff,metrics
      FROM scientific_hypothesis_evidence WHERE hypothesis_id=$1 ORDER BY created_at""",hypothesis_id)
    return [Evidence(str(r["experiment_key"]),str(r["symbol"]),str(r["regime"]),str(r["split_key"]),
        int(r["sample_count"]),float(r["mean_return_bps"]),float(r["hit_rate"]),float(r["cost_bps"]),
        str(r["dataset_cutoff"]) if r["dataset_cutoff"] is not None else None,
        dict(r["metrics"]) if r["metrics"] is not None else {}) for r in rows]

async def record_evidence(pool,hypothesis_id,spec:HypothesisSpec,evidence:Evidence,
                          min_samples=30,min_edge_bps=.5,min_hit_rate=.52):
    hypothesis_id=uuid.UUID(str(hypothesis_id))
    passed=evidence_passes(spec,evidence,min_samples,min_edge_bps,min_hit_rate)
    await pool.execute("""INSERT INTO scientific_hypothesis_evidence(
      id,hypothesis_id,experiment_key,symbol,regime,split_key,sample_count,
      mean_return_bps,hit_rate,cost_bps,dataset_cutoff,passed,metrics)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
      ON CONFLICT(hypothesis_id,experiment_key) DO UPDATE SET
      symbol=EXCLUDED.symbol,regime=EXCLUDED.regime,split_key=EXCLUDED.split_key,
      sample_count=EXCLUDED.sample_count,mean_return_bps=EXCLUDED.mean_return_bps,
      hit_rate=EXCLUDED.hit_rate,cost_bps=EXCLUDED.cost_bps,dataset_cutoff=EXCLUDED.dataset_cutoff,
      passed=EXCLUDED.passed,metrics=EXCLUDED.metrics,created_at=now()""",
      uuid.uuid4(),hypothesis_id,evidence.experiment_key,evidence.symbol,evidence.regime,
      evidence.split_key,int(evidence.sample_count),float(evidence.mean_return_bps),
      float(evidence.hit_rate),float(evidence.cost_bps),evidence.dataset_cutoff,bool(passed),
      json.dumps(evidence.details or {},sort_keys=True,separators=(",",":")))
    all_evidence=await _load_evidence(pool,hypothesis_id)
    state=lifecycle(spec,all_evidence,min_samples,min_edge_bps,min_hit_rate)
    await pool.execute("""UPDATE scientific_hypotheses SET status=$2,updated_at=now(),
      validated_at=CASE WHEN $2='VALIDATED' THEN COALESCE(validated_at,now()) ELSE validated_at END,
      rejected_at=CASE WHEN $2='REJECTED' THEN COALESCE(rejected_at,now()) ELSE rejected_at END
      WHERE id=$1""",hypothesis_id,state)
    if state=="REJECTED":
        await pool.execute("""INSERT INTO scientific_negative_memory(
          fingerprint,reason,evidence_count,cooldown_until,details)
          VALUES($1,$2,$3,now()+interval '30 days',$4::jsonb)
          ON CONFLICT(fingerprint) DO UPDATE SET reason=EXCLUDED.reason,
          evidence_count=EXCLUDED.evidence_count,cooldown_until=EXCLUDED.cooldown_until,
          details=EXCLUDED.details,updated_at=now()""",
          spec.fingerprint(),"independent evidence failed validation",len(all_evidence),
          json.dumps({"status":state},separators=(",",":")))
    return {"status":state,"evidence_count":len(all_evidence),"inserted_pass":bool(passed)}

async def negative_memory_active(pool,spec:HypothesisSpec):
    row=await pool.fetchrow("""SELECT reason,cooldown_until FROM scientific_negative_memory
      WHERE fingerprint=$1 AND (cooldown_until IS NULL OR cooldown_until>now())""",spec.fingerprint())
    return dict(row) if row else None
