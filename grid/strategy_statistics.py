import random,statistics
from math import isfinite, fsum

def _net(x):
    return float(x.get("pnl",0))-float(x.get("fees",0))-float(x.get("slippage",0))


def _finite_mean(values):
    # Preserve subnormal values/cancellation in the normal path. If even fsum
    # overflows before division, the stdlib exact-ratio mean avoids both that
    # overflow and the underflow caused by dividing each term first.
    if not values or any(not isfinite(value) for value in values):
        raise ValueError("bootstrap values must be finite")
    try:
        result = fsum(values) / len(values)
    except OverflowError:
        result = statistics.mean(values)
    if not isfinite(result):
        raise ValueError("bootstrap mean must be finite and representable")
    return result

def paired_expectancy_bootstrap(base_trades,variant_trades,key="signal_id",runs=1000,seed=17):
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    def indexed(trades):
        result = {}
        for trade in trades:
            identifier = trade.get(key)
            if identifier is None:
                continue
            if identifier in result:
                raise ValueError("duplicate trade identifier in paired bootstrap")
            value = _net(trade)
            if not isfinite(value):
                raise ValueError("trade net PnL must be finite")
            result[identifier] = trade
        return result
    b = indexed(base_trades)
    v = indexed(variant_trades)
    ids=sorted(set(b)&set(v),key=str)
    if len(ids)<2:return {"paired":len(ids),"delta_mean":None,"ci95":None}
    diffs=[_net(v[i])-_net(b[i]) for i in ids]
    delta_mean = _finite_mean(diffs)
    rng=random.Random(seed);means=[]
    for _ in range(int(runs)):
        means.append(_finite_mean([diffs[rng.randrange(len(diffs))] for _ in diffs]))
    means.sort()
    lo=means[int(.025*(len(means)-1))];hi=means[int(.975*(len(means)-1))]
    return {"paired":len(ids),"delta_mean":delta_mean,"ci95":[lo,hi],
            "positive_supported":lo>0,"negative_supported":hi<0}

def block_bootstrap_expectancy(trades,block_size=20,runs=1000,seed=23):
    if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
        raise ValueError("block_size must be a positive integer")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    pnl=[_net(x) for x in trades]
    if any(not isfinite(v) for v in pnl):
        raise ValueError("trade net PnL must be finite")
    if len(pnl)<max(2,block_size):return {"samples":len(pnl),"ci95":None}
    blocks=[pnl[i:i+block_size] for i in range(0,len(pnl),block_size) if len(pnl[i:i+block_size])==block_size]
    rng=random.Random(seed);means=[]
    for _ in range(int(runs)):
        sample=[]
        while len(sample)<len(pnl):sample.extend(blocks[rng.randrange(len(blocks))])
        sample=sample[:len(pnl)];means.append(_finite_mean(sample))
    means.sort()
    return {"samples":len(pnl),"blocks":len(blocks),
            "ci95":[means[int(.025*(len(means)-1))],means[int(.975*(len(means)-1))]]}
