import asyncio
import pytest

from grid.snapshot_pg_cluster_identity import (
    ClusterIdentityBlocked, verify_cluster_identity,
)


class Connection:
    def __init__(self, identity="123456789"):
        self.identity = identity

    async def fetchrow(self, query):
        assert "pg_control_system()" in query
        return {"system_identifier": self.identity}


def test_expected_cluster_identity_passes():
    result = asyncio.run(verify_cluster_identity(
        Connection(), expected_system_identifier="123456789"))
    assert result["status"] == "CLUSTER_IDENTITY_PASS"
    assert result["cross_source_coherence_attested"] is False


def test_wrong_cluster_rejected():
    with pytest.raises(ClusterIdentityBlocked, match="mismatch"):
        asyncio.run(verify_cluster_identity(
            Connection("999"), expected_system_identifier="123456789"))


def test_invalid_expected_identity_rejected():
    with pytest.raises(ClusterIdentityBlocked, match="Invalid"):
        asyncio.run(verify_cluster_identity(
            Connection(), expected_system_identifier=""))


def test_unavailable_identity_rejected():
    class Denied:
        async def fetchrow(self, query):
            raise PermissionError("not authorized")
    with pytest.raises(ClusterIdentityBlocked, match="unavailable"):
        asyncio.run(verify_cluster_identity(
            Denied(), expected_system_identifier="123456789"))
