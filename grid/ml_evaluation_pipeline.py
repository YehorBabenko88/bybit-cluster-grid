import json,uuid
from .trading_evaluation import evaluate_trades,stability_summary
from .ml_robustness import robustness_suite

async def record_oos_evaluation(pool,model_id,dataset_id,trades,evaluator_version="1"):
    report=evaluate_trades(trades); stability=stability_summary(report)
    metrics={"segments":report,"stability":stability}
    eid=uuid.uuid4()
    await pool.execute("""INSERT INTO model_evaluations
      (id,model_id,stage,dataset_id,metrics,passed,evaluator_version)
      VALUES($1,$2,'OOS',$3,$4::jsonb,false,$5)
      ON CONFLICT(model_id,stage,dataset_id) DO UPDATE SET metrics=EXCLUDED.metrics,
      passed=false,evaluator_version=EXCLUDED.evaluator_version,created_at=now()""",
      eid,model_id,dataset_id,json.dumps(metrics),evaluator_version)
    return metrics

async def record_robustness_evaluation(pool,model_id,dataset_id,trades,evaluator_version="1"):
    metrics=robustness_suite(trades);eid=uuid.uuid4()
    await pool.execute("""INSERT INTO model_evaluations
      (id,model_id,stage,dataset_id,metrics,passed,evaluator_version)
      VALUES($1,$2,'ROBUSTNESS',$3,$4::jsonb,false,$5)
      ON CONFLICT(model_id,stage,dataset_id) DO UPDATE SET metrics=EXCLUDED.metrics,
      passed=false,evaluator_version=EXCLUDED.evaluator_version,created_at=now()""",
      eid,model_id,dataset_id,json.dumps(metrics),evaluator_version)
    return metrics

async def apply_evaluation_gate(pool,model_id,stage,requirements):
    row=await pool.fetchrow("""SELECT id,metrics FROM model_evaluations
      WHERE model_id=$1 AND stage=$2 ORDER BY created_at DESC LIMIT 1""",model_id,stage)
    if not row:raise ValueError("evaluation missing")
    m=dict(row["metrics"]);base=(m.get("segments") or m.get("scenarios",{}).get("base") or {}).get("overall",{})
    stability=m.get("stability",{})
    if stage=="ROBUSTNESS" and "base" in stability: stability=stability["base"]
    passed=(base.get("trades",0)>=int(requirements.get("min_trades",100))
      and base.get("expectancy",0)>=float(requirements.get("min_expectancy",0))
      and (stability.get("positive_fraction") is not None)
      and stability.get("positive_fraction",0)>=float(requirements.get("min_positive_fraction",.6))
      and base.get("max_drawdown",float("inf"))<=float(requirements.get("max_drawdown",float("inf"))))
    if passed and stage=="ROBUSTNESS":
        # Base profitability is insufficient: every configured execution/cost
        # stress scenario must retain the required minimum expectancy.
        min_stress=float(requirements.get("min_stress_expectancy",requirements.get("min_expectancy",0)))
        scenarios=m.get("scenarios") or {}
        required_scenarios=("fees_x1_5","slippage_x2","execution_delay","drop_10pct","combined")
        passed=all(
            (scenarios.get(name) or {}).get("overall",{}).get("trades",0)>0
            and (scenarios.get(name) or {}).get("overall",{}).get("expectancy",float("-inf"))>=min_stress
            for name in required_scenarios
        )
    await pool.execute("UPDATE model_evaluations SET passed=$2 WHERE id=$1",row["id"],passed)
    if passed:
        target={"OOS":"OOS_PASSED","ROBUSTNESS":"ROBUSTNESS_PASSED"}.get(stage)
        if target:await pool.execute("UPDATE model_registry SET status=$2 WHERE id=$1",model_id,target)
    return passed


async def promote_production(pool,model_id):
    """Final fail-closed promotion. Training success is never sufficient."""
    async with pool.acquire() as c:
        async with c.transaction():
            model=await c.fetchrow("""SELECT id,dataset_id,feature_version,status FROM model_registry
              WHERE id=$1 FOR UPDATE""",model_id)
            if not model:raise ValueError("model missing")
            if model["status"]!="ROBUSTNESS_PASSED":
                raise ValueError("model has not passed robustness gate")
            stages=await c.fetch("""SELECT stage,dataset_id,passed FROM model_evaluations
              WHERE model_id=$1 AND stage IN ('OOS','ROBUSTNESS')
              ORDER BY created_at DESC""",model_id)
            latest={}
            for row in stages:
                latest.setdefault(row["stage"],row)
            for stage in ("OOS","ROBUSTNESS"):
                ev=latest.get(stage)
                if not ev or ev["passed"] is not True:
                    raise ValueError(stage+" evaluation has not passed")
                if ev["dataset_id"]!=model["dataset_id"]:
                    raise ValueError(stage+" evaluation dataset mismatch")
            ds=await c.fetchrow("""SELECT feature_version,status FROM dataset_snapshots
              WHERE id=$1""",model["dataset_id"])
            if not ds or ds["status"]!="READY":
                raise ValueError("model dataset is not READY")
            if ds["feature_version"]!=model["feature_version"]:
                raise ValueError("model feature version mismatch")
            await c.execute("UPDATE model_registry SET status='PRODUCTION' WHERE id=$1",model_id)
    return {"model_id":str(model_id),"status":"PRODUCTION"}
