import asyncio

from grid.control_candidate import ControlCandidate


class Journal:
    pass


def test_control_candidate_clears_epoch_on_database_failure(monkeypatch):
    async def scenario():
        async def failing_sync(pool, journal):
            raise ConnectionError("database unavailable")

        monkeypatch.setattr("grid.control_candidate.sync_control_to_local", failing_sync)
        candidate = ControlCandidate(None, "control-a", Journal(), lambda: [])
        candidate.election.is_leader = True
        candidate.election.epoch = 12345
        state = await candidate.tick()
        assert candidate.election.is_leader is False
        assert candidate.election.epoch is None
        assert state["leader"] is False
        assert state["mutations"] is False

    asyncio.run(scenario())
