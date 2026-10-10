import asyncio

from grid.control_plane import command_result


def test_command_completion_requires_active_delivery_lease():
    class Acquire:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def execute(self, sql, *args):
            assert "status='delivered'" in sql
            assert "lease_until>=now()" in sql
            assert args[1] == "done"
            return "UPDATE 0"
    class Pool:
        def acquire(self):
            return Acquire()
    asyncio.run(command_result(Pool(), "stale-id", True))


def test_failed_command_completion_uses_same_lease_guard():
    class Acquire:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def execute(self, sql, *args):
            assert "status='delivered'" in sql
            assert "lease_until>=now()" in sql
            assert args[1] == "failed"
            return "UPDATE 1"
    class Pool:
        def acquire(self):
            return Acquire()
    asyncio.run(command_result(Pool(), "current-id", False, error="failed"))
