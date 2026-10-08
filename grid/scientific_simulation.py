"""Deterministic execution-cost simulation for scientifically validated hypotheses.

This module has no exchange/order API. It consumes completed research outcomes only.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from math import sqrt,isfinite
import json

@dataclass(frozen=True)
class SimulationConfig:
    fee_bps:float=1.1
    base_slippage_bps:float=0.8
    half_spread_bps:float=0.6
    latency_ms:int=150
    latency_cost_bps_per_second:float=0.6
    funding_bps_per_8h:float=1.0
    min_fill_fraction:float=.55
    position_risk_fraction:float=.005
    max_drawdown:float=.12
    min_trades:int=100
    min_splits:int=3
    min_symbols:int=2
    min_expectancy_bps:float=.35
    min_profit_factor:float=1.10
    min_win_rate:float=.51
    max_single_split_share:float=.55
    monte_carlo_paths:int=200
    monte_carlo_max_dd_p95:float=.18

def deterministic_unit(key):
    raw=sha256(str(key).encode()).digest()
    return int.from_bytes(raw[:8],"big")/float(2**64-1)

def execution_costs(key,horizon_ms,cfg:SimulationConfig,stress=1.0):
    u=deterministic_unit(key)
    fill=max(float(cfg.min_fill_fraction),1.0-(u*.35*stress))
    slip=float(cfg.base_slippage_bps)*stress*(.75+.5*u)
    latency=float(cfg.latency_ms)/1000.0*float(cfg.latency_cost_bps_per_second)*stress
    funding=float(cfg.funding_bps_per_8h)*(float(horizon_ms)/(8*3600*1000))*stress
    fee=float(cfg.fee_bps)*stress
    spread=float(cfg.half_spread_bps)*stress
    return fill,fee,spread,slip,latency,funding

def simulate_rows(rows,direction,horizon_ms,cfg:SimulationConfig,stress=1.0):
    equity=1.0;peak=1.0;max_dd=0.0;trades=[];split_pnl={};symbols=set()
    wins=0;gross_win=0.0;gross_loss=0.0
    if isinstance(direction,bool) or int(direction) not in (-1,1):
        raise ValueError("simulation direction must be +1 or -1")
    if not isfinite(float(stress)) or stress<=0:
        raise ValueError("simulation stress must be finite and positive")
    sign=int(direction)
    previous_key=None
    for i,r in enumerate(rows):
        current_key=int(r["event_ts_ms"])
        if previous_key is not None and current_key<previous_key:
            raise ValueError("simulation rows must be chronological")
        previous_key=current_key
        key=f"{r['symbol']}|{r['event_ts_ms']}|{horizon_ms}"
        fill,fee,spread,slip,latency,funding=execution_costs(key,horizon_ms,cfg,stress)
        raw=float(r["return_bps"])
        if not isfinite(raw):
            raise ValueError("simulation return must be finite")
        net=(raw*sign-fee-spread-slip-latency-funding)*fill
        if not isfinite(net):
            raise ValueError("simulation net return must be finite")
        ret=net/10000.0*float(cfg.position_risk_fraction)/.005
        equity=max(1e-9,equity*(1.0+ret));peak=max(peak,equity)
        max_dd=max(max_dd,1.0-equity/peak)
        if net>0:wins+=1;gross_win+=net
        elif net<0:gross_loss+=-net
        split=str(r["split_key"]);split_pnl[split]=split_pnl.get(split,0.0)+net
        symbols.add(str(r["symbol"]))
        trades.append({"ordinal":i,"symbol":str(r["symbol"]),"event_ts_ms":int(r["event_ts_ms"]),
          "split_key":split,"raw_return_bps":raw,"net_return_bps":net,"fill_fraction":fill,
          "fee_bps":fee,"spread_bps":spread,"slippage_bps":slip,"latency_bps":latency,"funding_bps":funding,
          "equity_after":equity})
    n=len(trades);expectancy=sum(x["net_return_bps"] for x in trades)/n if n else 0.0
    pf=gross_win/gross_loss if gross_loss>1e-12 else (999.0 if gross_win>0 else 0.0)
    total_abs=sum(abs(v) for v in split_pnl.values())
    concentration=max((abs(v)/total_abs for v in split_pnl.values()),default=1.0)
    # Diagnostic uncertainty and costs: do not use these as proof of edge.
    net_values=[t["net_return_bps"] for t in trades]
    variance=sum((v-expectancy)**2 for v in net_values)/(n-1) if n>1 else 0.0
    standard_error=sqrt(variance/n) if n>1 else None
    lower_95=(expectancy-1.96*standard_error) if standard_error is not None else None
    total_fees=sum(t["fee_bps"]*t["fill_fraction"] for t in trades)
    total_spread=sum(t["spread_bps"]*t["fill_fraction"] for t in trades)
    total_slippage=sum(t["slippage_bps"]*t["fill_fraction"] for t in trades)
    total_latency=sum(t["latency_bps"]*t["fill_fraction"] for t in trades)
    total_funding=sum(t["funding_bps"]*t["fill_fraction"] for t in trades)
    losing_streak=0;max_losing_streak=0
    for v in net_values:
        losing_streak=losing_streak+1 if v<=0 else 0
        max_losing_streak=max(max_losing_streak,losing_streak)
    return {"trades":trades,"metrics":{"trades":n,"splits":len(split_pnl),"symbols":len(symbols),
      "expectancy_standard_error_bps":standard_error,"expectancy_lower_95_bps":lower_95,
      "max_consecutive_nonwinning_trades":max_losing_streak,
      "total_fee_bps":total_fees,"total_spread_bps":total_spread,
      "total_slippage_bps":total_slippage,"total_latency_bps":total_latency,
      "total_funding_bps":total_funding,
      "expectancy_bps":expectancy,"win_rate":wins/n if n else 0.0,"profit_factor":pf,
      "max_drawdown":max_dd,"final_equity":equity,"split_concentration":concentration,
      "split_pnl_bps":split_pnl}}

def deterministic_bootstrap_drawdowns(net_returns,paths=200,seed="simulation",position_scale=1.0):
    vals=list(map(float,net_returns))
    if any(not isfinite(v) for v in vals):
        raise ValueError("bootstrap returns must be finite")
    if not isfinite(float(position_scale)) or position_scale<0:
        raise ValueError("bootstrap position scale must be finite and nonnegative")
    if not vals:return [1.0]
    out=[];n=len(vals)
    for p in range(max(1,int(paths))):
        equity=1.0;peak=1.0;dd=0.0
        for i in range(n):
            u=deterministic_unit(f"{seed}|{p}|{i}")
            x=vals[min(n-1,int(u*n))]
            equity=max(1e-9,equity*(1.0+x/10000.0*float(position_scale)));peak=max(peak,equity);dd=max(dd,1-equity/peak)
        out.append(dd)
    return sorted(out)

def promotion_decision(metrics,stress_metrics,mc_drawdowns,cfg:SimulationConfig):
    p95=mc_drawdowns[min(len(mc_drawdowns)-1,int(.95*(len(mc_drawdowns)-1)))] if mc_drawdowns else 1.0
    checks={
      "min_trades":metrics["trades"]>=cfg.min_trades,
      "independent_splits":metrics["splits"]>=cfg.min_splits,
      "cross_symbol":metrics["symbols"]>=cfg.min_symbols,
      "expectancy":metrics["expectancy_bps"]>=cfg.min_expectancy_bps,
      "profit_factor":metrics["profit_factor"]>=cfg.min_profit_factor,
      "win_rate":metrics["win_rate"]>=cfg.min_win_rate,
      "drawdown":metrics["max_drawdown"]<=cfg.max_drawdown,
      "split_concentration":metrics["split_concentration"]<=cfg.max_single_split_share,
      "stress_expectancy":stress_metrics["expectancy_bps"]>0,
      "stress_profit_factor":stress_metrics["profit_factor"]>=1.0,
      "monte_carlo_drawdown":p95<=cfg.monte_carlo_max_dd_p95,
    }
    return all(checks.values()),checks,p95

def config_json(cfg):return json.dumps(asdict(cfg),sort_keys=True,separators=(",",":"))
