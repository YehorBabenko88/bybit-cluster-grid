"""Fail-closed immutable source set and routing epoch contract.

A matching manifest does not prove cross-store atomicity. Only a trusted
producer-issued source cut may attest coherence.
"""
from __future__ import annotations


class SourceEpochBlocked(ValueError):
    pass


def validate_source_epoch(receipts: list[dict], *, required_sources: frozenset[str],
                          expected_epoch: str, expected_routing_generation: int) -> None:
    if (not receipts or not required_sources or type(expected_epoch) is not str
            or not expected_epoch or type(expected_routing_generation) is not int
            or expected_routing_generation < 0):
        raise SourceEpochBlocked("Invalid source epoch requirements")
    required = {"source_id", "epoch_id", "routing_generation",
                "snapshot_id", "source_sha256"}
    seen = set()
    snapshot_ids = set()
    for receipt in receipts:
        if type(receipt) is not dict or set(receipt) != required:
            raise SourceEpochBlocked("Unsupported source receipt schema")
        if (type(receipt["source_id"]) is not str or not receipt["source_id"]
                or receipt["source_id"] in seen):
            raise SourceEpochBlocked("Duplicate or invalid source")
        seen.add(receipt["source_id"])
        if receipt["epoch_id"] != expected_epoch:
            raise SourceEpochBlocked("Mixed source epoch")
        if (type(receipt["routing_generation"]) is not int
                or receipt["routing_generation"] != expected_routing_generation):
            raise SourceEpochBlocked("Stale routing generation")
        if type(receipt["snapshot_id"]) is not str or not receipt["snapshot_id"]:
            raise SourceEpochBlocked("Missing source snapshot identity")
        if receipt["snapshot_id"] in snapshot_ids:
            raise SourceEpochBlocked("Reused source snapshot identity")
        snapshot_ids.add(receipt["snapshot_id"])
        digest = receipt["source_sha256"]
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise SourceEpochBlocked("Invalid source digest")
    if seen != required_sources:
        raise SourceEpochBlocked("Incomplete or unexpected source set")
