"""The original handover assertion now uses actual grants, not desired placements.

No network or real databases. PostgreSQL concurrency is tested separately in CI.
"""
import asyncio
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
import uuid

import pytest

sys.path.insert(0, os.environ.get("AUDIT_GRID_ROOT",
                                str(Path(__file__).resolve().parents[1] / "work" / "grid")))
from grid.config import settings
from grid.scheduler import stabilize_assignments
from grid.worker import Worker
from grid.collection_ownership import grant_assignments


class LeaseStore:
    """Unit persistence boundary; real unique-key/row locks have a PG gate."""
    def __init__(self,session):
        self.row={'owner':'old','session':uuid.UUID(session),'generation':1,'live':True}
    @asynccontextmanager
    async def acquire(self):yield self
    @asynccontextmanager
    async def transaction(self):yield self
    async def execute(self,sql,*args):
        assert sql.startswith('INSERT INTO collection_ownership')
    async def fetchrow(self,sql,*args):
        if sql.startswith('UPDATE'):
            self.row.update(owner=args[1],session=args[2],generation=args[3],live=True)
            return {'generation':args[3],'ttl':30}
        return self.row.copy()


def test_healthy_transfer_does_not_start_new_owner_before_old_owner_stops(monkeypatch, tmp_path):
    monkeypatch.setenv("ProgramData", str(tmp_path))

    async def scenario():
        symbols = [f"S{i}USDT" for i in range(10)]
        old = Worker()
        old.wanted = set(symbols)
        old.last_assignment_heartbeat = 100.0
        old.reconcile = AsyncMock()
        leases=LeaseStore(old.collector_session)
        assignment = stabilize_assignments(
            {"old": [], "new": symbols}, {"old": symbols, "new": []},
            {"old": {"pressure_state": "NORMAL"},
             "new": {"pressure_state": "NORMAL"}}, .1)
        assert len(assignment["new"]) == 1
        # New worker receives the replacement assignment first. The old
        # worker has not yet received its revocation heartbeat, and its
        # local lease is still valid at this point.
        new = Worker()
        new.wanted = set(await grant_assignments(leases,'new',new.collector_session,assignment['new']))
        assert not await old.expire_stale_assignments(now=100.1)
        assert old.wanted.isdisjoint(new.wanted), "old lease overlaps new assignment"
        leases.row['live']=False
        assert await old.expire_stale_assignments(now=100+3*settings.heartbeat_seconds+1)
        new.wanted=set(await grant_assignments(leases,'new',new.collector_session,assignment['new']))
        assert new.wanted=={'S0USDT'}
        assert old.wanted.isdisjoint(new.wanted)

    asyncio.run(scenario())
