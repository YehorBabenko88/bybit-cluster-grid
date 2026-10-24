import asyncio
import pytest

from grid.snapshot_pg_identity import ClusterIdentityBlocked, verify_cluster_identity


class FakeConnection:
    def __init__(self, identity):
        self.identity = identity

    async def fetchrow(self, query):
        assert "pg_control_system()" in query
        return {"system_identifier": self.identity}


def test_expected_identity_passes():
    result = asyncio.run(verify_cluster_identity(
        FakeConnection("123456789"), expected_system_identifier="123456789"))
    assert result["status"] == "CLUSTER_IDENTITY_PASS"
    assert result["coherent_snapshot_attested"] is False


@pytest.mark.parametrize("actual,expected", [
    ("123", "456"), ("123", ""), ("123", "not-numeric"),
    ("123", "１２３"),
])
def test_wrong_or_untrusted_identity_rejected(actual, expected):
    with pytest.raises(ClusterIdentityBlocked):
        asyncio.run(verify_cluster_identity(
            FakeConnection(actual), expected_system_identifier=expected))
