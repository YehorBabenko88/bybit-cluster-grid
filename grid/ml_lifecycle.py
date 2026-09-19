DATASET_TRANSITIONS={
 "BUILDING":{"READY","FAILED"},
 "READY":{"RETIRED"},
 "FAILED":set(),"RETIRED":set(),
}
MODEL_TRANSITIONS={
 "CANDIDATE":{"OOS_PASSED","REJECTED"},
 "OOS_PASSED":{"ROBUSTNESS_PASSED","REJECTED"},
 "ROBUSTNESS_PASSED":{"SHADOW","REJECTED"},
 "SHADOW":{"APPROVED","REJECTED"},
 "APPROVED":{"RETIRED"},
 "REJECTED":set(),"RETIRED":set(),
}

def allowed(mapping,current,target):
    return target in mapping.get(current,set())

async def transition_dataset(pool,dataset_id,target):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("SELECT status FROM dataset_snapshots WHERE id=$1 FOR UPDATE",dataset_id)
            if not row or not allowed(DATASET_TRANSITIONS,row["status"],target): return False
            await c.execute("UPDATE dataset_snapshots SET status=$2 WHERE id=$1",dataset_id,target)
            return True

async def transition_model(pool,model_id,target):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("SELECT status FROM model_registry WHERE id=$1 FOR UPDATE",model_id)
            if not row or not allowed(MODEL_TRANSITIONS,row["status"],target): return False
            await c.execute("""UPDATE model_registry SET status=$2,
              promoted_at=CASE WHEN $2='APPROVED' THEN now() ELSE promoted_at END WHERE id=$1""",model_id,target)
            return True
