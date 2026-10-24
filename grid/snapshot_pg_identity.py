"""Read-only PostgreSQL cluster identity guard.

Expected system_identifier must come from an independently trusted source.
This check is not a substitute for MVCC snapshot or source epoch attestation.
"""
class ClusterIdentityBlocked(ValueError):
    pass


async def verify_cluster_identity(connection, *, expected_system_identifier: str):
    if (type(expected_system_identifier) is not str
            or not expected_system_identifier.isascii()
            or not expected_system_identifier.isdecimal()
            or not expected_system_identifier):
        raise ClusterIdentityBlocked("Missing trusted cluster identity")
    row = await connection.fetchrow(
        "SELECT system_identifier::text AS system_identifier FROM pg_control_system()"
    )
    if row is None or row["system_identifier"] != expected_system_identifier:
        raise ClusterIdentityBlocked("PostgreSQL cluster identity mismatch")
    return {"status": "CLUSTER_IDENTITY_PASS",
            "system_identifier": expected_system_identifier,
            "coherent_snapshot_attested": False}
