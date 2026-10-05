import json
from .historical_signal_source import load_signals
from .historical_variant_engine import chronological_folds,select_validation
from .barrier_simulator import load_forward_candles,simulate_barrier
from .trading_evaluation import evaluate_trades
from .incremental_edge import compare_variant,paired_signal_effect
from .strategy_statistics import paired_expectancy_bootstrap,block_bootstrap_expectancy
from .event_conditioned_markov import EventConditionedMarkov
from .markov_training_data import attach_future_regime
from datetime import timedelta

async def _simulate(pool,signals,fold,sim_cfg):
    out=[]
    for i,s in enumerate(signals):
        x=dict(s)
        x["signal_id"]=x.get("signal_id") or f'{x["symbol"]}:{x["setup_type"]}:{x["event_ts"].isoformat()}'
        bars=await load_forward_candles(pool,x["symbol"],x["event_ts"],sim_cfg.get("horizon_bars",60))
        tr=simulate_barrier(x,bars,
          tp_bps=sim_cfg.get("tp_bps",40),sl_bps=sim_cfg.get("sl_bps",25),
          horizon_bars=sim_cfg.get("horizon_bars",60),fee_bps=sim_cfg.get("fee_bps",5.5),
          slippage_bps=sim_cfg.get("slippage_bps",1.5),
          notional=sim_cfg.get("notional",100.0))
        if tr:
            tr["fold"]=fold
            tr["state_from"]=x.get("state_from") or x.get("market_state")
            tr["markov_next"]=x.get("markov_next")
            tr["markov_scope"]=x.get("markov_scope")
            tr["markov_target_probability"]=x.get("markov_target_probability")
            out.append(tr)
    return out

async def run_symbol(pool,run_id,dataset_id,strategy_name,symbol,config):
    variants=config.get("variants",["BASE","REGIME","MARKOV","REGIME_MARKOV","ML","ML_MARKOV"])
    setups=config.get("setups",["POC","BREAKOUT","FALSE_BREAK","VOLATILITY_CAPTURE"])
    sim_cfg=config.get("simulation",{})
    min_train=int(config.get("min_train",100));fold_count=int(config.get("folds",4))
    threshold=float(config.get("markov_threshold",.55));ml_threshold=float(config.get("ml_threshold",.5))
    evidence={}
    for setup in setups:
        rows=await load_signals(pool,symbol,setup,config.get("start_ts"),config.get("end_ts"))
        folds=chronological_folds(rows,min_train=min_train,folds=fold_count)
        setup_result={}
        base_all=[]
        variant_all={v:[] for v in variants}
        availability={}
        for fold,train,val in folds:
            markov_horizon=int(config.get("markov_horizon_minutes",15))
            validation_start=min(x["event_ts"] for x in val)
            causal_train=[x for x in train if x["event_ts"]+timedelta(minutes=markov_horizon)<validation_start]
            markov_train=await attach_future_regime(pool,causal_train,markov_horizon)
            event_markov=EventConditionedMarkov(
              min_transitions=int(config.get("markov_min_transitions",30))).fit(markov_train)
            for variant in variants:
                selected,meta=select_validation(variant,setup,causal_train,val,
                  markov_threshold=threshold,ml_threshold=ml_threshold,
                  min_transitions=int(config.get("markov_min_transitions",30)),model=event_markov)
                trades=await _simulate(pool,selected,fold,sim_cfg)
                variant_all[variant].extend(trades)
                availability.setdefault(variant,[]).append(meta)
                if variant=="BASE":base_all.extend(trades)
        for variant,trades in variant_all.items():
            metrics=evaluate_trades(trades)
            inc=compare_variant(base_all,trades) if variant!="BASE" else None
            paired=paired_signal_effect(base_all,trades) if variant!="BASE" else None
            unc=paired_expectancy_bootstrap(base_all,trades,runs=int(config.get("bootstrap_runs",500))) if variant!="BASE" else block_bootstrap_expectancy(base_all,runs=int(config.get("bootstrap_runs",500)))
            unavailable=(variant in ("ML","ML_MARKOV") and any(x.get("missing_ml_score") for x in availability.get(variant,[])))
            setup_result[variant]={"metrics":metrics,"incremental":inc,"paired":paired,
              "uncertainty":unc,"availability":availability.get(variant,[]),"unavailable":unavailable}
            group=f"{run_id}:{symbol}:{setup}"
            await pool.execute("""INSERT INTO strategy_comparison_results
              (dataset_id,strategy_name,variant,comparison_group,metrics,incremental,uncertainty)
              VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb)
              ON CONFLICT(dataset_id,strategy_name,variant,comparison_group)
              DO UPDATE SET metrics=EXCLUDED.metrics,incremental=EXCLUDED.incremental,
                uncertainty=EXCLUDED.uncertainty,created_at=now()""",
              dataset_id,f"{strategy_name}:{setup}",variant,group,json.dumps(metrics,default=str),
              json.dumps({"comparison":inc,"paired":paired,"unavailable":unavailable},default=str) if variant!="BASE" else None,
              json.dumps(unc,default=str))
        evidence[setup]=setup_result
    return evidence
