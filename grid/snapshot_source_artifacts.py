"""Verify source receipt digests against immutable in-memory artifact bytes.

This is an integrity check, not signature verification or proof of coherence.
"""
from __future__ import annotations
from hashlib import sha256

from .snapshot_source_epoch import SourceEpochBlocked, validate_source_epoch


def verify_source_artifacts(
    receipts: list[dict], artifacts: dict[str, bytes], *,
    required_sources: frozenset[str], expected_epoch: str,
    expected_routing_generation: int, max_bytes_per_source: int,
) -> None:
    validate_source_epoch(
        receipts, required_sources=required_sources,
        expected_epoch=expected_epoch,
        expected_routing_generation=expected_routing_generation,
    )
    if type(max_bytes_per_source) is not int or max_bytes_per_source < 1:
        raise SourceEpochBlocked("Invalid artifact budget")
    if type(artifacts) is not dict or set(artifacts) != required_sources:
        raise SourceEpochBlocked("Incomplete artifact source set")
    for receipt in receipts:
        source = receipt["source_id"]
        data = artifacts[source]
        if type(data) is not bytes or len(data) > max_bytes_per_source:
            raise SourceEpochBlocked("Invalid or oversized source artifact")
        if sha256(data).hexdigest() != receipt["source_sha256"]:
            raise SourceEpochBlocked("Source artifact SHA256 mismatch")
