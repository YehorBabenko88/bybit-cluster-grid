import asyncio
import os
import uuid

import asyncpg
import pytest

from grid.migrations import MIGRATIONS


DSN = os.environ["POSTGRES_DSN"]


def test_production_evaluation_trigger_postgres_integration():
    async def scenario():
        conn = await asyncpg.connect(DSN)
        try:
            # Roll back all schema/data changes; do not interfere with other tests.
            async with conn.transaction():
                await conn.execute("CREATE TEMP TABLE model_registry (id uuid PRIMARY KEY, status text NOT NULL)")
                await conn.execute("CREATE TEMP TABLE model_evaluations (id uuid PRIMARY KEY, model_id uuid NOT NULL, passed boolean NOT NULL, dataset_id uuid, stage text)")
                statements = [sql for version, _, sqls in MIGRATIONS if version in (45, 46) for sql in sqls]
                # PostgreSQL resolves the temporary tables before permanent tables.
                for sql in statements:
                    await conn.execute(sql)
                model_id, evaluation_id = uuid.uuid4(), uuid.uuid4()
                await conn.execute("INSERT INTO model_registry VALUES ($1,'CANDIDATE')", model_id)
                await conn.execute("INSERT INTO model_evaluations VALUES ($1,$2,false)", evaluation_id, model_id)
                await conn.execute("UPDATE model_registry SET status='PRODUCTION' WHERE id=$1", model_id)
                for statement, args in (
                    ("UPDATE model_evaluations SET passed=true WHERE id=$1", (evaluation_id,)),
                    ("DELETE FROM model_evaluations WHERE id=$1", (evaluation_id,)),
                    ("INSERT INTO model_evaluations VALUES ($1,$2,true)", (uuid.uuid4(), model_id)),
                ):
                    with pytest.raises(asyncpg.PostgresError, match="immutable"):
                        async with conn.transaction():
                            await conn.execute(statement, *args)
                assert await conn.fetchval("SELECT passed FROM model_evaluations WHERE id=$1", evaluation_id) is False
                await conn.execute("UPDATE model_registry SET status='CANDIDATE' WHERE id=$1", model_id)
                for column in ("model_id", "dataset_id", "stage"):
                    value = uuid.uuid4() if column != "stage" else "ROBUSTNESS"
                    with pytest.raises(asyncpg.PostgresError, match="identity is immutable"):
                        async with conn.transaction():
                            await conn.execute(
                                "UPDATE model_evaluations SET " + column + "=$1 WHERE id=$2",
                                value, evaluation_id,
                            )
                await conn.execute("UPDATE model_registry SET status='PRODUCTION' WHERE id=$1", model_id)
                # Roll back deliberately at the outer transaction boundary.
                raise _Rollback()
        except _Rollback:
            pass
        finally:
            await conn.close()
    asyncio.run(scenario())


class _Rollback(Exception):
    pass



def test_concurrent_production_promotion_blocks_evaluation_write():
    async def scenario():
        a = await asyncpg.connect(DSN)
        b = await asyncpg.connect(DSN)
        model_id, evaluation_id = uuid.uuid4(), uuid.uuid4()
        try:
            await a.execute("CREATE TABLE IF NOT EXISTS model_registry (id uuid PRIMARY KEY, status text NOT NULL)")
            await a.execute("CREATE TABLE IF NOT EXISTS model_evaluations (id uuid PRIMARY KEY, model_id uuid NOT NULL, passed boolean NOT NULL, dataset_id uuid, stage text)")
            for sql in (sql for version, _, sqls in MIGRATIONS if version in (45, 46) for sql in sqls):
                await a.execute(sql)
            await a.execute("INSERT INTO model_registry VALUES ($1,'CANDIDATE')", model_id)
            await a.execute("INSERT INTO model_evaluations VALUES ($1,$2,false)", evaluation_id, model_id)
            started = asyncio.Event()

            async def competing_update():
                async with b.transaction():
                    started.set()
                    await b.execute("UPDATE model_evaluations SET passed=true WHERE id=$1", evaluation_id)

            async with a.transaction():
                await a.execute("UPDATE model_registry SET status='PRODUCTION' WHERE id=$1", model_id)
                task = asyncio.create_task(competing_update())
                await asyncio.wait_for(started.wait(), 5)
                await asyncio.sleep(0.2)
                assert not task.done(), "write should wait for the promotion row lock"
            with pytest.raises(asyncpg.PostgresError, match="immutable"):
                await asyncio.wait_for(task, 5)
            assert await a.fetchval("SELECT passed FROM model_evaluations WHERE id=$1", evaluation_id) is False
        finally:
            await a.execute("UPDATE model_registry SET status='CANDIDATE' WHERE id=$1", model_id)
            await a.execute("DELETE FROM model_evaluations WHERE model_id=$1", model_id)
            await a.execute("DELETE FROM model_registry WHERE id=$1", model_id)
            await a.close()
            await b.close()

    asyncio.run(scenario())
