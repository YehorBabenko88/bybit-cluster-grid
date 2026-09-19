async def store_transition_edges(pool,dataset_id,model_id,strategy_name,symbol,edges):
    async with pool.acquire() as c:
        async with c.transaction():
            for e in edges:
                await c.execute("""INSERT INTO markov_transition_edges
                  (dataset_id,model_id,strategy_name,symbol,setup_type,state_from,state_to,trades,net_pnl,expectancy,hit_rate)
                  VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                  ON CONFLICT(dataset_id,model_id,strategy_name,symbol,setup_type,state_from,state_to)
                  DO UPDATE SET trades=EXCLUDED.trades,net_pnl=EXCLUDED.net_pnl,
                    expectancy=EXCLUDED.expectancy,hit_rate=EXCLUDED.hit_rate,created_at=now()""",
                  dataset_id,model_id,strategy_name,symbol,e["setup_type"],e["state_from"],e["state_to"],
                  e["trades"],e["net_pnl"],e["expectancy"],e["hit_rate"])
