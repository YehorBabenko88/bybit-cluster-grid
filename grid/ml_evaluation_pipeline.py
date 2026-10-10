import json,uuid
from math import isfinite


def _finite_number(value,default=float('nan')):
    try:
        number=float(value)
        return number if isfinite(number) else default
    except (TypeError,ValueError,OverflowError):
        return default

from .trading_evaluation import evaluate_trades,stability_summary
from .ml_robustness import robustness_suite

async def record_oos_evaluation(pool,model_id,dataset_id,trades,evaluator_version="1"):
    report=evaluate_trades(trades); stability=stability_summary(report)
    metrics={"segments":report,"stability":stability}
    eid=uuid.uuid4()
    async with pool.acquire() as c:
        async with c.transaction():
            model=await c.fetchrow("SELECT id,dataset_id,status FROM model_registry WHERE id=$1 FOR UPDATE",model_id)
            if not model or model["dataset_id"]!=dataset_id:
                raise ValueError("model dataset mismatch")
            if model["status"]=="PRODUCTION":
                raise ValueError("production model evaluations are immutable; create a new candidate")
            await c.execute("""INSERT INTO model_evaluations
      (id,model_id,stage,dataset_id,metrics,passed,evaluator_version)
      VALUES($1,$2,'OOS',$3,$4::jsonb,false,$5)
      ON CONFLICT(model_id,stage,dataset_id) DO UPDATE SET metrics=EXCLUDED.metrics,
      passed=false,evaluator_version=EXCLUDED.evaluator_version,created_at=now()""",
              eid,model_id,dataset_id,json.dumps(metrics),evaluator_version)
            await c.execute("""UPDATE model_registry SET status='REJECTED'
              WHERE id=$1 AND status IN ('OOS_PASSED','ROBUSTNESS_PASSED')""",model_id)
            # A new OOS result invalidates any earlier robustness pass too.
            await c.execute("""UPDATE model_evaluations SET passed=false
              WHERE model_id=$1 AND stage='ROBUSTNESS'""",model_id)
    return metrics

async def record_robustness_evaluation(pool,model_id,dataset_id,trades,evaluator_version="1"):
    metrics=robustness_suite(trades);eid=uuid.uuid4()
    async with pool.acquire() as c:
        async with c.transaction():
            model=await c.fetchrow("SELECT id,dataset_id,status FROM model_registry WHERE id=$1 FOR UPDATE",model_id)
            if not model or model["dataset_id"]!=dataset_id:
                raise ValueError("model dataset mismatch")
            if model["status"]=="PRODUCTION":
                raise ValueError("production model evaluations are immutable; create a new candidate")
            await c.execute("""INSERT INTO model_evaluations
      (id,model_id,stage,dataset_id,metrics,passed,evaluator_version)
      VALUES($1,$2,'ROBUSTNESS',$3,$4::jsonb,false,$5)
      ON CONFLICT(model_id,stage,dataset_id) DO UPDATE SET metrics=EXCLUDED.metrics,
      passed=false,evaluator_version=EXCLUDED.evaluator_version,created_at=now()""",
              eid,model_id,dataset_id,json.dumps(metrics),evaluator_version)
            await c.execute("""UPDATE model_registry SET status='OOS_PASSED'
              WHERE id=$1 AND status='ROBUSTNESS_PASSED'""",model_id)
    return metrics

def _validated_requirements(requirements):
    """Reject malformed or permissive gate configuration before database writes."""
    if not isinstance(requirements,dict):
        raise ValueError("evaluation requirements must be a dictionary")
    values=dict(requirements)
    for key in ("min_expectancy","min_positive_fraction","max_drawdown","min_stress_expectancy"):
        if key in values:
            value=_finite_number(values[key])
            if not isfinite(value):
                raise ValueError("invalid evaluation requirement: "+key)
            values[key]=value
    if "min_trades" in values:
        try:
            count=int(values["min_trades"])
        except (TypeError,ValueError,OverflowError):
            raise ValueError("invalid evaluation requirement: min_trades") from None
        if count<1 or str(values["min_trades"]).strip() not in (str(count),):
            raise ValueError("invalid evaluation requirement: min_trades")
        values["min_trades"]=count
    if not 0<=values.get("min_positive_fraction",0.6)<=1:
        raise ValueError("invalid min_positive_fraction")
    if values.get("max_drawdown",float("inf"))<0:
        raise ValueError("invalid max_drawdown")
    return values


def _valid_stress_scenario(scenario,min_expectancy):
    if not isinstance(scenario,dict):
        return False
    overall=scenario.get("overall")
    if not isinstance(overall,dict):
        return False
    trades=_finite_number(overall.get("trades"))
    expectancy=_finite_number(overall.get("expectancy"))
    drawdown=_finite_number(overall.get("max_drawdown"))
    return (isfinite(trades) and trades>0 and trades.is_integer()
        and isfinite(expectancy) and expectancy>=min_expectancy
        and isfinite(drawdown) and drawdown>=0)


async def apply_evaluation_gate(pool,model_id,stage,requirements):
    """Atomically persist evaluation and model status under a model row lock."""
    if stage not in ("OOS","ROBUSTNESS"):
        raise ValueError("unsupported evaluation stage")
    requirements=_validated_requirements(requirements)
    async with pool.acquire() as c:
        async with c.transaction():
            return await _apply_evaluation_gate_locked(c,model_id,stage,requirements)

async def _apply_evaluation_gate_locked(c,model_id,stage,requirements):
    if stage not in ("OOS","ROBUSTNESS"):
        raise ValueError("unsupported evaluation stage")
    requirements=_validated_requirements(requirements)
    model=await c.fetchrow("SELECT id,dataset_id,feature_version,status FROM model_registry WHERE id=$1 FOR UPDATE",model_id)
    if not model: raise ValueError("model missing")
    if model["status"]=="PRODUCTION":
        raise ValueError("production model evaluations are immutable; create a new candidate")
    ds=await c.fetchrow("""SELECT status,feature_version FROM dataset_snapshots
      WHERE id=$1""",model["dataset_id"])
    if not ds or ds["status"]!="READY" or ds["feature_version"]!=model["feature_version"]:
        raise ValueError("model dataset is not READY or feature version mismatches")
    row=await c.fetchrow("""SELECT e.id,e.metrics FROM model_evaluations e
      JOIN model_registry m ON m.id=e.model_id AND m.dataset_id=e.dataset_id
      WHERE e.model_id=$1 AND e.stage=$2 ORDER BY e.created_at DESC,e.id DESC LIMIT 1""",model_id,stage)
    if not row:raise ValueError("evaluation missing")
    m=dict(row["metrics"]);base=(m.get("segments") or m.get("scenarios",{}).get("base") or {}).get("overall",{})
    stability=m.get("stability",{})
    if stage=="ROBUSTNESS" and "base" in stability: stability=stability["base"]
    # A fraction and a drawdown are bounded statistics; impossible values
    # indicate corrupted or incompatible evaluation evidence.
    trades=_finite_number(base.get("trades"))
    expectancy=_finite_number(base.get("expectancy"))
    drawdown=_finite_number(base.get("max_drawdown"))
    positive_fraction=_finite_number(stability.get("positive_fraction"))
    metrics_valid=(isfinite(trades) and trades>=0 and trades.is_integer()
      and isfinite(expectancy) and isfinite(drawdown) and drawdown>=0
      and isfinite(positive_fraction) and 0<=positive_fraction<=1)
    passed=metrics_valid and (_finite_number(base.get("trades"))>=int(requirements.get("min_trades",100))
      and _finite_number(base.get("expectancy"))>=float(requirements.get("min_expectancy",0))
      and (stability.get("positive_fraction") is not None)
      and _finite_number(stability.get("positive_fraction"))>=float(requirements.get("min_positive_fraction",.6))
      and _finite_number(base.get("max_drawdown"))<=float(requirements.get("max_drawdown",float("inf"))))
    if passed and stage=="ROBUSTNESS":
        # Base profitability is insufficient: every configured execution/cost
        # stress scenario must retain the required minimum expectancy.
        min_stress=float(requirements.get("min_stress_expectancy",requirements.get("min_expectancy",0)))
        scenarios=m.get("scenarios") or {}
        required_scenarios=("fees_x1_5","slippage_x2","execution_delay","drop_10pct","combined")
        passed=all(
            _valid_stress_scenario(scenarios.get(name),min_stress)
            for name in required_scenarios
        )
    await c.execute("UPDATE model_evaluations SET passed=$2 WHERE id=$1",row["id"],passed)
    if stage=="OOS":
        # Any OOS re-evaluation changes the evidence underpinning robustness.
        # Require a fresh robustness gate even if the new OOS result passes.
        await c.execute("""UPDATE model_evaluations SET passed=false
          WHERE model_id=$1 AND stage='ROBUSTNESS'""",model_id)
        await c.execute("""UPDATE model_registry SET status='OOS_PASSED'
          WHERE id=$1 AND status='ROBUSTNESS_PASSED' AND $2=true""",model_id,passed)
    if passed:
        target={"OOS":"OOS_PASSED","ROBUSTNESS":"ROBUSTNESS_PASSED"}[stage]
        # Never downgrade a robustness-approved model on an OOS recheck.
        # Robustness may advance only a model that already passed OOS.
        if stage=="OOS":
            await c.execute("""UPDATE model_registry SET status=$2
              WHERE id=$1 AND status IN ('CANDIDATE','REJECTED','OOS_PASSED')""",model_id,target)
        else:
            await c.execute("""UPDATE model_registry SET status=$2
              WHERE id=$1 AND status IN ('OOS_PASSED','ROBUSTNESS_PASSED')""",model_id,target)
    else:
        # A failed re-evaluation must invalidate any prior pre-production pass.
        # Production models require an explicit separate rollback decision.
        await c.execute("""UPDATE model_registry SET status='REJECTED'
          WHERE id=$1 AND status IN ('OOS_PASSED','ROBUSTNESS_PASSED')""",model_id)
    if passed and stage=="ROBUSTNESS":
        oos=await c.fetchrow("""SELECT passed FROM model_evaluations
          WHERE model_id=$1 AND stage='OOS' AND dataset_id=$2
          ORDER BY created_at DESC,id DESC LIMIT 1""",model_id,model["dataset_id"])
        if not oos or oos["passed"] is not True:
            raise ValueError("robustness requires a passing OOS evaluation")
        # A gate is successful only if the model actually reached the target state.
        current=await c.fetchval("SELECT status FROM model_registry WHERE id=$1",model_id)
        if current not in ("ROBUSTNESS_PASSED","PRODUCTION"):
            raise ValueError("robustness evaluation cannot advance model before OOS")
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
              ORDER BY created_at DESC,id DESC""",model_id)
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
