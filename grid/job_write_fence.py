"""Job ownership guard for independent PostgreSQL writers."""
import asyncio
from contextlib import asynccontextmanager


class StaleJobWrite(RuntimeError):
    pass


@asynccontextmanager
async def job_write(pool, kind, job_id, owner, generation, timeout_seconds=None):
    if not owner or isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise StaleJobWrite('missing job ownership identity')
    if kind == 'ml':
        lock_sql = 'SELECT id FROM ml_jobs WHERE id=$1 FOR UPDATE'
        remaining_sql = """SELECT EXTRACT(EPOCH FROM (lease_until-clock_timestamp()))
          FROM ml_jobs WHERE id=$1 AND status='running' AND lease_owner=$2
          AND lease_generation=$3 AND lease_until>clock_timestamp()"""
        args = (job_id, owner, generation)
    elif kind == 'strategy':
        if timeout_seconds is None or timeout_seconds <= 0:
            raise StaleJobWrite('invalid strategy timeout')
        lock_sql = 'SELECT id FROM strategy_jobs WHERE id=$1 FOR UPDATE'
        remaining_sql = """SELECT EXTRACT(EPOCH FROM
          (started_at+($4*interval '1 second')-clock_timestamp())) FROM strategy_jobs
          WHERE id=$1 AND status='running' AND assigned_node=$2 AND attempts=$3
          AND started_at+($4*interval '1 second')>clock_timestamp()"""
        args = (job_id, owner, generation, float(timeout_seconds))
    else:
        raise ValueError('unknown job fence kind')
    try:
        async with asyncio.timeout(None) as timer:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    if not await connection.fetchrow(lock_sql, job_id):
                        raise StaleJobWrite('job not found')
                    # PostgreSQL now() is fixed at transaction start. Read the
                    # actual clock AFTER waiting for the ownership row lock.
                    anchor = asyncio.get_running_loop().time()
                    remaining = await connection.fetchval(remaining_sql, *args)
                    if remaining is None or float(remaining) <= 0:
                        raise StaleJobWrite('job ownership expired or replaced')
                    deadline = anchor + float(remaining)
                    timer.reschedule(deadline)
                    yield connection
                    remaining = await connection.fetchval(remaining_sql, *args)
                    if remaining is None or float(remaining) <= 0:
                        raise StaleJobWrite('job ownership lost before commit')
                    # The outer timer covers deferred constraints in COMMIT.
    except TimeoutError as exc:
        raise StaleJobWrite('job deadline expired during publication') from exc
