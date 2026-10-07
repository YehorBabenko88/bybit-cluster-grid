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
    node_scores={n:s for n,s in node_scores.items() if (nodes.get(n,{}) or {}).get("accepts_work",True)}
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


def stabilize_assignments(proposed,current,nodes,max_churn_fraction=.10):
    """Keep healthy assignments sticky; pressure/offline moves immediately."""
    proposed={n:list(v) for n,v in proposed.items()}
    current=current or {}
    live=set(proposed)
    forced=set()
    for n,syms in current.items():
        state=(nodes.get(n,{}).get("pressure_state") or "OFFLINE").upper()
        if n not in live or state in ("REDUCE_LOAD","CRITICAL"):
            forced.update(syms)
    # Proposed remains authoritative for forced moves. For healthy nodes, cap churn.
    old_owner={s:n for n,syms in current.items() for s in syms}
    new_owner={s:n for n,syms in proposed.items() for s in syms}
    moves=[s for s,n in new_owner.items() if old_owner.get(s) not in (None,n) and s not in forced]
    cap=max(1,int(max(1,len(new_owner))*float(max_churn_fraction)))
    allowed=set(sorted(moves)[:cap])
    out={n:[] for n in proposed}
    for symbol,new in new_owner.items():
        old=old_owner.get(symbol)
        if old in live and symbol not in forced and old!=new and symbol not in allowed:
            out[old].append(symbol)
        else:
            out[new].append(symbol)
    return out
