from dataclasses import dataclass

INSTALLING="INSTALLING"
DB_READY="DB_READY"
DISCOVERING="DISCOVERING"
COLLECTING="COLLECTING"
WARMING="WARMING"
RESEARCH_READY="RESEARCH_READY"

@dataclass(frozen=True)
class ColdStartPolicy:
    min_candles_per_symbol:int=1440
    min_feature_rows_per_symbol:int=720
    min_symbols:int=1
    min_poc_events:int=20
    min_level_events:int=20

async def readiness(pool,policy=ColdStartPolicy()):
    tables=await pool.fetch("""SELECT table_name FROM information_schema.tables
      WHERE table_schema='public'""")
    names={r["table_name"] for r in tables}
    required={"candles_1m","market_features_1m","poc_lifecycle","level_events"}
    if not required.issubset(names):
        return {"state":DB_READY,"ready":False,"reason":"schema_incomplete"}

    symbols=await pool.fetchval("SELECT count(DISTINCT symbol) FROM candles_1m")
    if not symbols:
        return {"state":COLLECTING,"ready":False,"symbols":0,"reason":"no_market_data"}

    rows=await pool.fetch("""SELECT c.symbol,count(*) candles,
      (SELECT count(*) FROM market_features_1m f WHERE f.symbol=c.symbol) features
      FROM candles_1m c GROUP BY c.symbol""")
    mature=[r for r in rows if r["candles"]>=policy.min_candles_per_symbol
            and r["features"]>=policy.min_feature_rows_per_symbol]
    poc=await pool.fetchval("SELECT count(*) FROM poc_lifecycle WHERE first_touch_ts IS NOT NULL")
    levels=await pool.fetchval("SELECT count(*) FROM level_events")
    ready=(len(mature)>=policy.min_symbols and poc>=policy.min_poc_events and levels>=policy.min_level_events)
    return {"state":RESEARCH_READY if ready else WARMING,"ready":ready,
      "symbols":symbols,"mature_symbols":len(mature),"poc_events":poc,"level_events":levels,
      "reason":None if ready else "insufficient_history"}

def research_allowed(snapshot):
    return bool(snapshot.get("ready")) and snapshot.get("state")==RESEARCH_READY
