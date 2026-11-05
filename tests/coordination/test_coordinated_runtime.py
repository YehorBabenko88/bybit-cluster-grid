import asyncio
from types import SimpleNamespace
import pytest
from grid.floating_leader import FloatingLeader


class Pool:
    async def fetchval(self, *args): return True
    async def execute(self, *args): return 'UPDATE 1'


class Authority:
    config = SimpleNamespace(request_timeout=.1)
    async def validate(self, lease): return True
    async def release(self, lease): pass


class Leader(FloatingLeader):
    def __init__(self):
        super().__init__(Pool(), 'node-a', renew_seconds=.005, coordination=Authority())
        self.campaigns = 0
        self.renews = 0
    async def campaign(self):
        self.campaigns += 1
        if self.campaigns > 1:
            self.stop()
            return False
        self.is_leader = True; self.epoch = 42
        self.coordination_lease = SimpleNamespace(owner='node-a', token=17, session_id='owned')
        return True
    async def renew(self):
        self.renews += 1
        return True
    async def release(self, epoch): pass


def test_slow_initializer_does_not_starve_lease_renewal():
    async def scenario():
        leader = Leader()
        renewed = asyncio.Event()
        cleaned = []
        async def renew():
            leader.renews += 1; renewed.set(); return True
        leader.renew = renew
        async def gain(epoch):
            await asyncio.wait_for(renewed.wait(), timeout=.05)
            leader.stop()
        async def loss(): cleaned.append(True)
        await asyncio.wait_for(leader.run(gain, loss), timeout=.2)
        assert leader.renews > 0
        assert cleaned == [True]
        assert not leader.is_leader and leader.epoch is None
    asyncio.run(scenario())


def test_cancellation_stops_partial_initializer_and_cleans_writer():
    async def scenario():
        leader = Leader(); started = asyncio.Event(); cleaned = []
        async def gain(epoch): started.set(); await asyncio.Event().wait()
        async def loss(): cleaned.append(True)
        task = asyncio.create_task(leader.run(gain, loss))
        await asyncio.wait_for(started.wait(), .1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert cleaned == [True]
        assert not leader.is_leader and leader.epoch is None
    asyncio.run(scenario())


def test_failed_writer_cleanup_requires_fencing_and_never_recampaigns():
    async def scenario():
        leader = Leader()
        async def renew(): leader.is_leader = False; leader.epoch = None; return False
        leader.renew = renew
        async def gain(epoch): pass
        async def loss(): raise RuntimeError('writer state unknown')
        await asyncio.wait_for(leader.run(gain, loss), .2)
        assert leader.campaigns == 1
        assert leader.requires_fencing is True and leader.stop_event.is_set()
        assert not leader.is_leader and leader.epoch is None
    asyncio.run(scenario())


def test_configured_ha_cannot_start_coordinator_via_legacy_pg_fallback(monkeypatch):
    async def scenario():
        import grid.coordinator as coordinator
        settings = SimpleNamespace(grid_coordination_mode='legacy', grid_ha_required=True)
        monkeypatch.setattr(coordinator, 'settings', settings)
        async def forbidden_db(): raise AssertionError('invalid HA must be rejected before database startup')
        monkeypatch.setattr(coordinator, 'prepare_database', forbidden_db)
        with pytest.raises(ValueError, match='Consul'):
            await coordinator.startup()
    asyncio.run(scenario())


def test_control_candidate_accepts_explicit_dcs_without_degraded_mutation_fallback():
    from grid.control_candidate import ControlCandidate
    candidate = ControlCandidate(Pool(), 'node-a', None, lambda: [], coordination=Authority(), ha_required=True)
    assert candidate.election.coordination is not None


def test_database_startup_failure_closes_created_coordination_client(monkeypatch):
    async def scenario():
        import grid.coordinator as coordinator
        closed = []
        class Created:
            async def close(self): closed.append(True)
        async def create(settings, **kwargs): return Created()
        async def fail(): raise RuntimeError('startup database failure')
        monkeypatch.setattr(coordinator, 'coordinator_authority', create)
        monkeypatch.setattr(coordinator, 'prepare_database', fail)
        monkeypatch.setattr(coordinator, 'bootstrap_logging', lambda: None)
        with pytest.raises(RuntimeError, match='startup database failure'):
            await coordinator.startup()
        assert closed == [True]
        monkeypatch.setattr(coordinator, 'coordination_authority', None)
    asyncio.run(scenario())


def test_production_ha_rejects_unqualified_external_watchdog():
    async def scenario():
        from grid.coordination import coordinator_authority
        settings = SimpleNamespace(grid_coordination_mode='consul', grid_ha_required=True,
                                   grid_coordination_isolated_lab=False)
        with pytest.raises(ValueError, match='external writer fence/watchdog'):
            await coordinator_authority(settings)
    asyncio.run(scenario())


def test_pg_guard_deadline_does_not_allow_hung_resource_check_to_authorize_writer():
    async def scenario():
        from grid.coordination import floating_leader_guard, CoordinationUnavailable
        leader = Leader()
        await leader.campaign()
        async def stalled(*args):
            await asyncio.sleep(.2)
            return True
        leader.pool.fetchval = stalled
        with pytest.raises(CoordinationUnavailable):
            await floating_leader_guard(leader)()
    asyncio.run(scenario())
