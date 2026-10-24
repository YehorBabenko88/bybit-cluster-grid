"""Verify synthetic immutable partition payload against its manifest.

Never infer historical availability, revisions or source epochs. This is
consumer-side structural verification, not producer authentication.
"""
from __future__ import annotations
import hashlib
import json

from .snapshot_partition_contract import PartitionContractError


def verify_partition_payload(partition: dict, payload: bytes, *, max_bytes: int) -> None:
    if type(max_bytes) is not int or max_bytes < 1:
        raise PartitionContractError("Invalid byte limit")
    if type(payload) is not bytes or len(payload) > max_bytes:
        raise PartitionContractError("Payload exceeds byte limit")
    if hashlib.sha256(payload).hexdigest() != partition["artifact_sha256"]:
        raise PartitionContractError("Payload SHA256 mismatch")
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise PartitionContractError("Duplicate JSON key")
            obj[key] = value
        return obj
    try:
        rows = json.loads(payload, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError) as exc:
        raise PartitionContractError("Invalid payload JSON") from exc
    if type(rows) is not list or len(rows) != partition["row_count"]:
        raise PartitionContractError("Payload row count mismatch")
    seen = set()
    last = None
    for row in rows:
        if type(row) is not dict or set(row) != {"event_ns", "available_ns", "revision"}:
            raise PartitionContractError("Unexpected row schema")
        event, available, revision = (row[k] for k in ("event_ns", "available_ns", "revision"))
        if any(type(v) is not int or v < 0 for v in (event, available, revision)):
            raise PartitionContractError("Invalid row timestamps/revision")
        if revision < 1 or event > available or available > partition["knowledge_cutoff_ns"]:
            raise PartitionContractError("Noncausal row")
        if event in seen or (last is not None and event <= last):
            raise PartitionContractError("Duplicate or unordered event")
        seen.add(event)
        last = event
    if rows and (rows[0]["event_ns"] != partition["first_event_ns"]
                 or rows[-1]["event_ns"] != partition["last_event_ns"]):
        raise PartitionContractError("Manifest range mismatch")
