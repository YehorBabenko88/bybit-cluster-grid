async def attach_future_regime(pool,rows,horizon_minutes=15):
    out=[]
    for r in rows:
        x=dict(r)
        state=await pool.fetchval("""SELECT regime FROM market_features_1m
          WHERE symbol=$1 AND ts>=$2+($3*interval '1 minute')
          ORDER BY ts LIMIT 1""",x["symbol"],x["event_ts"],int(horizon_minutes))
        x["state_to"]=state
        out.append(x)
    return out
