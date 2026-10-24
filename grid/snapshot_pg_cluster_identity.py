"""Conservative PostgreSQL cluster identity attestation.

A caller must provide a trusted expected system_identifier. The identifier
must be obtained from an authorized source; this function does not infer it
from database names or hostnames. Read-only SQL only.
"""
from __future__ import annotations


class ClusterIdentityBlocked(ValueError):
    pass


async def verify_cluster_identity(connection, *, expected_system_identifier: str) -> dict:
    if (type(expected_system_identifier) is not str
            or not expected_system_identifier.isdecimal()
            or not expected_system_identifier):
        raise ClusterIdentityBlocked("Invalid trusted cluster identifier")
    try:
        row = await connection.fetchrow(
            "SELECT system_identifier::text AS system_identifier FROM pg_control_system()"
        )
    except Exception as exc:
        raise ClusterIdentityBlocked("Cluster identity unavailable") from exc
    if row is None or str(row["system_identifier"]) != expected_system_identifier:
        raise ClusterIdentityBlocked("PostgreSQL cluster identity mismatch")
    return {"status": "CLUSTER_IDENTITY_PASS",
            "system_identifier": expected_system_identifier,
            "cross_source_coherence_attested": False}
