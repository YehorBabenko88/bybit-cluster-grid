from __future__ import annotations


async def load_microstructure_samples(pool,symbol,start=None,end=None,limit=None):
    """Return causal ML snapshot payloads in chronological order.

    Payload keys intentionally match StratTester's attach_live_microstructure
    contract, so no feature reconstruction is required at export time.
    """
    where=["symbol=$1"]; args=[str(symbol)]
    if start is not None:
        args.append(start); where.append(f"ts>=${len(args)}")
    if end is not None:
        args.append(end); where.append(f"ts<${len(args)}")
    sql="SELECT payload FROM microstructure_samples WHERE "+" AND ".join(where)+" ORDER BY ts"
    if limit is not None:
        args.append(int(limit)); sql+=f" LIMIT ${len(args)}"
    rows=await pool.fetch(sql,*args)
    return [dict(r["payload"]) for r in rows]
