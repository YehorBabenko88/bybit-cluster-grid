import math
from statistics import median

def learned_symbol_cost(nodes, default=1.0):
    samples={}
    for node in nodes.values():
        for symbol,cost in (node.get("symbol_cost") or {}).items():
            try:
                value=float(cost)
            except (TypeError,ValueError):
                continue
            if math.isfinite(value) and value>0:
                samples.setdefault(symbol,[]).append(value)
    known=[v for vals in samples.values() for v in vals]
    try:
        baseline=float(default)
    except (TypeError,ValueError,OverflowError):
        baseline=1.0
    if not math.isfinite(baseline) or baseline<=0:
        baseline=1.0
    fallback=median(known) if known else baseline
    return {symbol:median(vals) for symbol,vals in samples.items()},max(baseline,fallback)

def node_avoids(node,symbol):
    state=(node.get("pressure_state") or "NORMAL").upper()
    drained=set(node.get("drained_symbols") or [])
    if state=="CRITICAL":
        return True
    return state=="REDUCE_LOAD" and symbol in drained

def weighted_assign(symbols,node_scores,nodes):
    # A missing, zero, negative, or non-finite capacity cannot safely take work.
    eligible_scores={}
    for node_id,raw_score in node_scores.items():
        if not (nodes.get(node_id,{}) or {}).get("accepts_work",True):
            continue
        try:
            score=float(raw_score)
        except (TypeError,ValueError,OverflowError):
            continue
        if math.isfinite(score) and score>0:
            eligible_scores[node_id]=score
    node_scores=eligible_scores
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
            # A CRITICAL node must never receive a new assignment, even
            # when every available machine is overloaded. Pause collection
            # rather than force work onto a machine reporting emergency state.
            eligible=[n for n in node_scores if
                      (nodes.get(n,{}).get("pressure_state") or "NORMAL").upper()!="CRITICAL"]
            if not eligible:
                continue
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
    try:
        churn=float(max_churn_fraction)
    except (TypeError,ValueError,OverflowError):
        churn=0.0
    if not math.isfinite(churn):
        churn=0.0
    cap=max(0,int(len(new_owner)*max(0.0,min(1.0,churn))))
    allowed=set(sorted(moves)[:cap])
    out={n:[] for n in proposed}
    for symbol,new in new_owner.items():
        old=old_owner.get(symbol)
        if old in live and symbol not in forced and old!=new and symbol not in allowed:
            out[old].append(symbol)
        else:
            out[new].append(symbol)
    return out
