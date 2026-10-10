"""Route persisted market events into scientific micro agents."""
from __future__ import annotations
import json

async def route_market_event(orchestrator,pool,symbol,ts_ms,event_type,payload,split_key,source_event_id=None):
    symbol=str(symbol);ts=int(ts_ms);p=dict(payload or {})
    signals=[];matured={"labels":[],"hypothesis_updates":[]}
    if event_type=="trade_tape_250ms":
        price=_num(p.get("close"))
        volume=_num(p.get("buy_volume"),0.0)+_num(p.get("sell_volume"),0.0)
        delta=_num(p.get("delta"),0.0)
        if price is not None and price>0:
            orchestrator.latest_trade[symbol]=(ts,price)
            matured=await orchestrator.observe_price(pool,symbol,ts,price)
        signals.extend([
            orchestrator.delta_agent.update(symbol,ts,delta,volume),
            orchestrator.volume_agent.update(symbol,ts,volume,delta),
        ])
    elif event_type=="derivatives_ticker":
        oi=p.get("open_interest")
        if oi is not None:
            signals.append(orchestrator.oi_agent.update(
                symbol,ts,oi,p.get("last_price") or p.get("mark_price")))
    elif event_type=="orderbook_snapshot":
        signals.append(orchestrator.book_agent.update(symbol,ts,p))
        signals.append(orchestrator.wall_agent.update(symbol,ts,p.get("walls") or []))
    else:
        return {"processed":False,"reason":"event_type_not_research_input","scheduled":0}

    ref=orchestrator.latest_trade.get(symbol)
    fresh_ref=ref is not None and 0<=ts-int(ref[0])<=3000
    scheduled=0;hypotheses=[]
    for signal in signals:
        await _persist_signal(pool,signal,source_event_id)
        consensus=orchestrator.consensus.update(signal)
        if signal.state!="EXCITED" or not fresh_ref:
            continue
        result=await orchestrator.ingest_micro_signal(
            pool,signal,float(ref[1]),split_key,consensus_result=consensus)
        scheduled+=int(result.get("scheduled") or 0)
        hypotheses.extend(result.get("hypotheses") or [])
    return {"processed":True,"signals":len(signals),"scheduled":scheduled,
            "hypotheses":hypotheses,"matured":matured}

async def _persist_signal(pool,signal,source_event_id=None):
    await pool.execute("""INSERT INTO micro_agent_signals(
      symbol,event_ts,agent,state,score,direction,features,source_event_id)
      VALUES($1,to_timestamp($2/1000.0),$3,$4,$5,$6,$7::jsonb,$8)
      ON CONFLICT(source_event_id,agent) WHERE source_event_id IS NOT NULL DO UPDATE SET
      state=EXCLUDED.state,score=EXCLUDED.score,direction=EXCLUDED.direction,features=EXCLUDED.features""",
      signal.symbol,int(signal.ts_ms),signal.agent,signal.state,float(signal.score),
      int(signal.direction),json.dumps(signal.features,sort_keys=True,separators=(",",":")),
      int(source_event_id) if source_event_id is not None else None)

def _num(v,default=None):
    try:return float(v) if v is not None else default
    except (TypeError,ValueError):return default
