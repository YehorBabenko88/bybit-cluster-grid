"""Pure validation of a proposed immutable Grid export partition manifest.

No database, filesystem or network access. Source epochs and timestamps must
be producer-issued; this validator never derives missing historical facts.
"""
from __future__ import annotations


class PartitionContractError(ValueError):
    pass


def validate_partitions(partitions: list[dict], *, expected_epoch: str) -> None:
    if type(expected_epoch) is not str or not expected_epoch or not partitions:
        raise PartitionContractError("Missing expected epoch or partitions")
    required = {
        "source_id", "epoch_id", "exchange", "market_type", "symbol",
        "dataset", "timeframe_ns", "first_event_ns", "last_event_ns",
        "knowledge_cutoff_ns", "row_count", "artifact_sha256",
    }
    seen = {}
    for p in partitions:
        if type(p) is not dict or set(p) != required:
            raise PartitionContractError("Unexpected partition schema")
        for name in ("source_id", "epoch_id", "exchange", "market_type",
                     "symbol", "dataset"):
            if type(p[name]) is not str or not p[name]:
                raise PartitionContractError("Invalid partition identity")
        if p["epoch_id"] != expected_epoch:
            raise PartitionContractError("Mixed coherence epochs")
        for name in ("timeframe_ns", "first_event_ns", "last_event_ns",
                     "knowledge_cutoff_ns", "row_count"):
            if type(p[name]) is not int or p[name] < 0:
                raise PartitionContractError("Invalid partition integer")
        if p["timeframe_ns"] == 0 or p["row_count"] == 0:
            raise PartitionContractError("Empty or invalid partition")
        if not p["first_event_ns"] <= p["last_event_ns"] <= p["knowledge_cutoff_ns"]:
            raise PartitionContractError("Noncausal partition range")
        digest = p["artifact_sha256"]
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PartitionContractError("Invalid digest shape")
        key = (p["exchange"], p["market_type"], p["symbol"],
               p["dataset"], p["timeframe_ns"])
        intervals = seen.setdefault(key, [])
        for first, last, source in intervals:
            if not (p["last_event_ns"] < first or p["first_event_ns"] > last):
                raise PartitionContractError("Overlapping or duplicate partition authority")
        intervals.append((p["first_event_ns"], p["last_event_ns"], p["source_id"]))
