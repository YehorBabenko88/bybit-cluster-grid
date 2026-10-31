"""PostgreSQL promotion boundary. DCS and hard-fence verification are external.

A database lease in the failed PostgreSQL cluster cannot authorize its own
promotion. Supply a linearizable independent DCS verifier and a fencing backend
which proves the previous writer cannot resume. Missing/unknown checks deny.
"""
import asyncio
import re

class HAError(RuntimeError):
    pass


def lsn_bytes(value):
    if type(value) is not str or not re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}', value):
        raise ValueError('invalid PostgreSQL LSN')
    high, low = value.split('/')
    return (int(high, 16) << 32) + int(low, 16)


def replication_health(primary_lsn, replay_lsn, max_lag_bytes):
    if type(max_lag_bytes) is not int or max_lag_bytes < 0:
        raise ValueError('invalid lag budget')
    try:
        lag = lsn_bytes(primary_lsn) - lsn_bytes(replay_lsn)
        if lag < 0:
            raise ValueError('divergent timeline or sample')
        return {'state': 'HEALTHY' if lag <= max_lag_bytes else 'LAGGING', 'lag_bytes': lag}
    except ValueError:
        return {'state': 'UNKNOWN', 'lag_bytes': None}


class PostgresAdapter:
    """asyncpg-compatible dedicated standby connection; caller owns credentials.

    Never configure a production DSN implicitly. The controller's verification
    callbacks must bind candidate/epoch to this connection's cluster identity.
    """
    def __init__(self, connection):
        self.connection = connection

    async def recovery(self):
        return await self.connection.fetchval('SELECT pg_is_in_recovery()')

    async def replay_lsn(self):
        return await self.connection.fetchval('SELECT pg_last_wal_replay_lsn()::text')

    async def promote(self):
        return await self.connection.fetchval('SELECT pg_promote(true, 10)')


class PromotionController:
    def __init__(self, postgres, verify_lease, verify_fence, timeout=5, *, acknowledged_lsn=None, fence_candidate=None):
        if not callable(verify_lease) or not callable(verify_fence):
            raise ValueError('independent DCS and fence verifiers required')
        if type(timeout) not in (int, float) or not 0 < timeout <= 30:
            raise ValueError('bounded verification timeout required')
        self.postgres, self.lease, self.fence, self.timeout = postgres, verify_lease, verify_fence, timeout
        self.acknowledged_lsn = acknowledged_lsn
        self.fence_candidate = fence_candidate
        self.lock = asyncio.Lock()

    async def _verified(self, function, *args):
        try:
            result = await asyncio.wait_for(function(*args), timeout=self.timeout)
        except Exception as exc:
            raise HAError('verification unavailable') from exc
        if result is not True:
            raise HAError('verification denied or unknown')

    async def _postgres_call(self, operation):
        # Server-side SQL timeouts do not bound a stalled network response.
        try:
            return await asyncio.wait_for(operation(), timeout=self.timeout)
        except Exception as exc:
            raise HAError('PostgreSQL operation unavailable or outcome unknown') from exc

    async def promote(self, candidate, old_primary, epoch, required_lsn):
        if (any(type(v) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', v) for v in (candidate, old_primary))
                or candidate == old_primary or type(epoch) is not int or not 1 <= epoch < 2**63):
            raise HAError('promotion identity/epoch invalid')
        required = lsn_bytes(required_lsn)
        async with self.lock:
            await self._verified(self.lease, candidate, epoch)
            await self._verified(self.fence, old_primary, epoch)
            if not callable(self.acknowledged_lsn):
                raise HAError('trusted durable acknowledged LSN unavailable')
            try:
                committed = await asyncio.wait_for(self.acknowledged_lsn(candidate, epoch), self.timeout)
                if lsn_bytes(committed) != required:
                    raise HAError('required LSN differs from durable control state')
            except HAError:
                raise
            except Exception as exc:
                raise HAError('durable acknowledged LSN unknown') from exc
            if not callable(self.fence_candidate):
                raise HAError('candidate emergency fence backend required')
            if await self._postgres_call(self.postgres.recovery) is not True:
                raise HAError('candidate is not a standby')
            if lsn_bytes(await self._postgres_call(self.postgres.replay_lsn)) < required:
                raise HAError('candidate has not replayed required durable commit')
            await self._verified(self.lease, candidate, epoch)
            await self._verified(self.fence, old_primary, epoch)
            # A promotion timeout may still have changed the writer role. Fence
            # candidate on any promotion/post-verification failure, including
            # cancellation; never leave an unknown writable candidate running.
            try:
                if await self._postgres_call(self.postgres.promote) is not True:
                    raise HAError('promotion not confirmed')
                await self._verified(self.lease, candidate, epoch)
                await self._verified(self.fence, old_primary, epoch)
            except BaseException:
                await asyncio.shield(self._verified(self.fence_candidate, candidate, epoch))
                raise
            return {'status': 'PROMOTED', 'candidate': candidate, 'epoch': epoch,
                    'required_lsn': required_lsn, 'physical_admission': 'NOT_GRANTED'}

    async def supervise_writer(self, candidate, epoch, stop_event, *, interval=.5):
        """Local watchdog for the existing Grid runner; it does not elect leaders.

        External DCS authority owns renewals. Loss, unavailable verification,
        shutdown or cancellation fences this local writer before returning.
        A service-level watchdog must also fence on process/host death.
        """
        if type(interval) not in (int,float) or not 0 < interval <= 5 or not callable(self.fence_candidate):
            raise HAError('bounded writer watchdog and fence backend required')
        try:
            while not stop_event.is_set():
                await self._verified(self.lease,candidate,epoch)
                try:
                    await asyncio.wait_for(stop_event.wait(),interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            await asyncio.shield(self._verified(self.fence_candidate,candidate,epoch))
