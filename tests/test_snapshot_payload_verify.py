import hashlib
import json
import pytest

from grid.snapshot_payload_verify import verify_partition_payload
from grid.snapshot_partition_contract import PartitionContractError


def fixture(rows):
    payload = json.dumps(rows, separators=(",", ":")).encode()
    part = dict(artifact_sha256=hashlib.sha256(payload).hexdigest(),
                row_count=len(rows), timeframe_ns=120, knowledge_cutoff_ns=300,
                first_event_ns=0, last_event_ns=120)
    return part, payload


def test_valid_payload():
    part, payload = fixture([
        dict(event_ns=0, available_ns=60, revision=1),
        dict(event_ns=120, available_ns=180, revision=1)])
    verify_partition_payload(part, payload, max_bytes=1000)


def test_tampered_payload_rejected():
    part, payload = fixture([dict(event_ns=0, available_ns=60, revision=1)])
    with pytest.raises(PartitionContractError, match="SHA256"):
        verify_partition_payload(part, payload+b"x", max_bytes=1000)


def test_duplicate_event_rejected():
    rows = [dict(event_ns=0, available_ns=60, revision=1)] * 2
    part, payload = fixture(rows)
    part["last_event_ns"] = 0
    with pytest.raises(PartitionContractError, match="Duplicate"):
        verify_partition_payload(part, payload, max_bytes=1000)


def test_future_availability_rejected():
    part, payload = fixture([dict(event_ns=0, available_ns=301, revision=1)])
    with pytest.raises(PartitionContractError, match="Noncausal"):
        verify_partition_payload(part, payload, max_bytes=1000)


def test_oversized_payload_rejected():
    part, payload = fixture([dict(event_ns=0, available_ns=60, revision=1)])
    with pytest.raises(PartitionContractError, match="byte limit"):
        verify_partition_payload(part, payload, max_bytes=1)


def test_internal_gap_rejected():
    part, payload = fixture([
        dict(event_ns=0, available_ns=60, revision=1),
        dict(event_ns=240, available_ns=250, revision=1),
    ])
    part["last_event_ns"] = 240
    with pytest.raises(PartitionContractError, match="Gap"):
        verify_partition_payload(part, payload, max_bytes=1000)
