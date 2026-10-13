import asyncio

from grid.floating_leader import FloatingLeader
from grid.leader_bound_service import LeaderBoundService


def test_failed_loss_is_retried_before_reacquiring_and_restarting_service():
    """A failed stop must not carry a running singleton into the next epoch."""
    async def scenario():
        events = []
        stopped = asyncio.Event()

        async def start(epoch):
            events.append(("start", epoch))
            if epoch == 2:
                stopped.set()

        attempts = 0

        async def stop():
            nonlocal attempts
            attempts += 1
            events.append(("stop", attempts))
            if attempts == 1:
                raise ConnectionError("service shutdown interrupted")

        service = LeaderBoundService(start, stop)

        class Election(FloatingLeader):
            async def campaign(self):
                epoch = 1 if not events else 2
                events.append(("campaign", epoch))
                self.is_leader, self.epoch = True, epoch
                return True

            async def renew(self):
                self.is_leader, self.epoch = False, None
                return False

        leader = Election(None, node_id="control", renew_seconds=.001)
        task = asyncio.create_task(leader.run(service.gain, service.lose))
        try:
            await asyncio.wait_for(stopped.wait(), .1)
        finally:
            leader.stop()
            await asyncio.wait_for(task, 1)
        assert events[:6] == [
            ("campaign", 1), ("start", 1), ("stop", 1),
            ("stop", 2), ("campaign", 2), ("start", 2),
        ]

    asyncio.run(scenario())


def test_persistent_cleanup_failure_blocks_new_campaigns():
    async def scenario():
        campaigns = 0
        stops = 0

        class Election(FloatingLeader):
            async def campaign(self):
                nonlocal campaigns
                campaigns += 1
                self.is_leader, self.epoch = True, campaigns
                return True

            async def renew(self):
                self.is_leader, self.epoch = False, None
                return False

        leader = Election(None, renew_seconds=.001)

        async def loss():
            nonlocal stops
            stops += 1
            if stops == 3:
                leader.stop()
            raise ConnectionError("cannot stop old service")

        await asyncio.wait_for(leader.run(on_loss=loss), 1)
        assert campaigns == 1
        assert stops == 3
        assert not leader.is_leader and leader.epoch is None

    asyncio.run(scenario())
