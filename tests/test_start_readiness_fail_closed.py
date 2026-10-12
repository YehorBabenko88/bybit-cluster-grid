"""Regression guard: an unreadable fleet operation registry must block START."""
import asyncio
from grid.start_readiness import start_readiness


class Pool:
    async def fetchval(self, sql):
        return 1

    async def fetch(self, sql):
        return [{"node_id": "pc4"}]

    async def fetchrow(self, sql, *args):
        raise RuntimeError("fleet registry unavailable")


def test_start_blocks_when_fleet_operations_cannot_be_read():
    import time
    nodes = {"pc4": {"last_seen": time.time(), "integrity_ok": True}}
    result = asyncio.run(start_readiness(Pool(), nodes, heartbeat_seconds=30))
    assert result["ready"] is False
    assert "fleet_operations_unavailable" in result["missing"]
