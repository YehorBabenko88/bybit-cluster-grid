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
                await conn.execute("CREATE TEMP TABLE model_evaluations (id uuid PRIMARY KEY, model_id uuid NOT NULL, passed boolean NOT NULL)")
                statements = next(sqls for version, _, sqls in MIGRATIONS if version == 45)
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
                # Roll back deliberately at the outer transaction boundary.
                raise _Rollback()
        except _Rollback:
            pass
        finally:
            await conn.close()
    asyncio.run(scenario())


class _Rollback(Exception):
    pass
