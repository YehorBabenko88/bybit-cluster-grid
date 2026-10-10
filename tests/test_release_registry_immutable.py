import asyncio
import pytest

from grid.update_protocol import register_release


class FakeConnection:
    def __init__(self):
        self.record = None

    async def execute(self, sql, version, channel, url, sha, metadata):
        if self.record is None:
            self.record = {"package_url": url, "sha256": sha}

    async def fetchrow(self, sql, version):
        return self.record


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()

    def acquire(self):
        return self

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


def test_registered_artifact_is_immutable():
    async def run():
        pool = FakePool()
        await register_release(pool, "v1", "candidate", "https://example.test/v1.zip", "a" * 64)
        await register_release(pool, "v1", "candidate", "https://example.test/v1.zip", "a" * 64)
        with pytest.raises(ValueError, match="different artifact"):
            await register_release(pool, "v1", "candidate", "https://example.test/other.zip", "a" * 64)
        with pytest.raises(ValueError, match="different artifact"):
            await register_release(pool, "v1", "candidate", "https://example.test/v1.zip", "b" * 64)
        assert pool.conn.record == {"package_url": "https://example.test/v1.zip", "sha256": "a" * 64}
    asyncio.run(run())
