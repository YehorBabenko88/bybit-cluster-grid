async def reserved_by_node(pool):
    rows=await pool.fetch("""SELECT node_id,COALESCE(sum(cpu),0) cpu,COALESCE(sum(ram_gb),0) ram_gb,
      COALESCE(sum(scratch_gb),0) scratch_gb,COALESCE(bool_or(gpu),false) gpu,count(*) jobs FROM ml_resource_reservations
      WHERE expires_at>=now() GROUP BY node_id""")
    return {r["node_id"]:dict(r) for r in rows}

async def reserve(pool,job_id,node_id,workload,seconds=120):
    r=await pool.execute("""INSERT INTO ml_resource_reservations
      (job_id,node_id,cpu,ram_gb,scratch_gb,gpu,expires_at)
      VALUES($1,$2,$3,$4,$5,$6,now()+($7*interval '1 second'))
      ON CONFLICT(job_id) DO NOTHING""",job_id,node_id,float(workload.cpu),float(workload.ram_gb),
      float(workload.scratch_gb),bool(workload.gpu),int(seconds))
    return r.endswith(" 1")

async def release(pool,job_id):
    await pool.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)

async def purge_expired(pool):
    return await pool.execute("DELETE FROM ml_resource_reservations WHERE expires_at<now()")
