import asyncio
from grid.floating_leader import FloatingLeader


class Pool:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        if self.fail:
            raise RuntimeError("database unavailable")
        return "UPDATE 1"


def test_failed_gain_releases_only_its_own_epoch():
    async def scenario():
        pool = Pool()
        leader = FloatingLeader(pool, node_id="node-a", renew_seconds=0.01)

        async def campaign():
            leader.is_leader = True
            leader.epoch = 42
            return True

        async def on_gain(epoch):
            assert epoch == 42
            leader.stop()
            raise RuntimeError("initialization failed")

        leader.campaign = campaign
        await asyncio.wait_for(leader.run(on_gain=on_gain), timeout=1)
        assert leader.is_leader is False
        assert leader.epoch is None
        assert len(pool.calls) == 1
        sql, args = pool.calls[0]
        assert "owner=$1" in sql
        assert "(metadata->>'epoch')::bigint=$2" in sql
        assert args == ("node-a", 42)

    asyncio.run(scenario())


def test_failed_gain_release_error_does_not_restore_leadership():
    async def scenario():
        pool = Pool(fail=True)
        leader = FloatingLeader(pool, node_id="node-a", renew_seconds=0.01)

        async def campaign():
            leader.is_leader = True
            leader.epoch = 7
            return True

        async def on_gain(epoch):
            leader.stop()
            raise RuntimeError("initialization failed")

        leader.campaign = campaign
        await asyncio.wait_for(leader.run(on_gain=on_gain), timeout=1)
        assert len(pool.calls) == 1
        assert leader.is_leader is False
        assert leader.epoch is None

    asyncio.run(scenario())
