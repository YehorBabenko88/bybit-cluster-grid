def markov_context(model,row):
    state=row.get("market_state") or row.get("regime")
    p,meta=model.probabilities(row.get("symbol"),row.get("setup_type"),state)
    return {"state_from":state,"markov_scope":list(meta["scope"]),
            "markov_transitions":meta["transitions"],"markov_next":p,
            "markov_p_stay":p.get(state,0.0),
            "markov_p_high_vol":sum(v for k,v in p.items() if k in ("HIGH_VOL","IMPULSE"))}

def enrich_simulated_trade(model,signal,trade):
    out=dict(trade);out.update(markov_context(model,signal))
    out.setdefault("symbol",signal.get("symbol"))
    out.setdefault("setup_type",signal.get("setup_type"))
    out.setdefault("regime",signal.get("regime") or signal.get("market_state"))
    return out

def transition_edge(trades):
    buckets={}
    for t in trades:
        key=(t.get("state_from"),t.get("state_to"),t.get("setup_type"))
        x=buckets.setdefault(key,{"trades":0,"net_pnl":0.0,"wins":0})
        pnl=float(t.get("pnl",0))-float(t.get("fees",0))-float(t.get("slippage",0))
        x["trades"]+=1;x["net_pnl"]+=pnl;x["wins"]+=int(pnl>0)
    return [{"state_from":k[0],"state_to":k[1],"setup_type":k[2],"trades":v["trades"],
             "net_pnl":v["net_pnl"],"expectancy":v["net_pnl"]/v["trades"],
             "hit_rate":v["wins"]/v["trades"]} for k,v in sorted(buckets.items(),key=lambda z:str(z[0]))]
