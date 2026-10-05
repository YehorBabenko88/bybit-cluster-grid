EXPECTED_COLUMN_TYPES={
 "candles_1m":{"symbol":"text","ts":"timestamp with time zone","open":"numeric","high":"numeric",
               "low":"numeric","close":"numeric","trade_count":"integer","quality_reasons":"jsonb"},
 "footprint_1m":{"symbol":"text","ts":"timestamp with time zone","price":"numeric",
                 "buy_count":"integer","sell_count":"integer"},
 "market_events":{"id":"bigint","symbol":"text","event_ts":"timestamp with time zone","payload":"jsonb"},
 "market_features_1m":{"symbol":"text","ts":"timestamp with time zone","eligible":"boolean",
                       "regime":"text","regime_score":"double precision","features":"jsonb"},
 "ml_jobs":{"id":"uuid","payload":"jsonb","priority":"integer","lease_generation":"bigint",
            "lease_until":"timestamp with time zone"},
 "ml_artifacts":{"id":"uuid","bytes":"bigint","reusable":"boolean","expires_at":"timestamp with time zone"},
}

async def schema_type_audit(pool):
    tables=list(EXPECTED_COLUMN_TYPES)
    rows=await pool.fetch("""SELECT table_name,column_name,data_type
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name=ANY($1::text[])""",tables)
    actual={(r["table_name"],r["column_name"]):r["data_type"] for r in rows}
    missing=[];mismatch=[]
    for table,columns in EXPECTED_COLUMN_TYPES.items():
        for column,expected in columns.items():
            got=actual.get((table,column))
            if got is None:missing.append(f"{table}.{column}")
            elif got!=expected:mismatch.append({"column":f"{table}.{column}","expected":expected,"actual":got})
    return {"ok":not missing and not mismatch,"missing":missing,"mismatch":mismatch,
            "checked":sum(len(x) for x in EXPECTED_COLUMN_TYPES.values())}
