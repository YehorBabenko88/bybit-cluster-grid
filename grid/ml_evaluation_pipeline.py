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
    await pool.execute("UPDATE model_evaluations SET passed=$2 WHERE id=$1",row["id"],passed)
    if passed:
        target={"OOS":"OOS_PASSED","ROBUSTNESS":"ROBUSTNESS_PASSED"}.get(stage)
        if target:await pool.execute("UPDATE model_registry SET status=$2 WHERE id=$1",model_id,target)
    return passed
