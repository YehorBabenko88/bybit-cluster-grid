from statistics import median

def learned_symbol_cost(nodes, default=1.0):
    samples={}
    for node in nodes.values():
        for symbol,cost in (node.get("symbol_cost") or {}).items():
            try:
                value=float(cost)
            except (TypeError,ValueError):
                continue
            if value>0:
                samples.setdefault(symbol,[]).append(value)
    known=[v for vals in samples.values() for v in vals]
    fallback=median(known) if known else float(default)
    return {symbol:median(vals) for symbol,vals in samples.items()},max(float(default),fallback)

def node_avoids(node,symbol):
    state=(node.get("pressure_state") or "NORMAL").upper()
    drained=set(node.get("drained_symbols") or [])
    if state=="CRITICAL":
        return True
    return state=="REDUCE_LOAD" and symbol in drained

def weighted_assign(symbols,node_scores,nodes):
    result={n:[] for n in node_scores}
    if not node_scores:
        return result
    costs,fallback=learned_symbol_cost(nodes)
    load={n:0.0 for n in node_scores}
    # Expensive-first greedy placement avoids clustering several heavy markets on one node.
    ordered=sorted(symbols,key=lambda s:(costs.get(s,fallback),s),reverse=True)
    for symbol in ordered:
        cost=max(.01,costs.get(symbol,fallback))
        eligible=[n for n in node_scores if not node_avoids(nodes.get(n,{}),symbol)]
        if not eligible:
            # Preserve only a tiny priority core under fleet-wide CRITICAL pressure.
            # Never put the whole universe back onto overloaded machines.
            if symbol!="BTCUSDT" and any(x=="BTCUSDT" for x in symbols):
                continue
            eligible=[min(node_scores,key=lambda n:(load[n]/node_scores[n],n))]
        node=min(eligible,key=lambda n:(load[n]/node_scores[n],n))
        result[node].append(symbol)
        load[node]+=cost
    return result
