"""Pure, fail-closed regular-bar coverage verification for exported partitions.

Use only for explicitly regular candle datasets. A valid manifest is not a
proof of source-owned availability history or cross-store MVCC coherence.
"""
from __future__ import annotations

from .snapshot_partition_contract import PartitionContractError, validate_partitions


def validate_regular_partition_coverage(
    partitions: list[dict],
    *,
    expected_epoch: str,
    expected_ranges: dict[tuple, tuple[int, int]],
) -> None:
    validate_partitions(partitions, expected_epoch=expected_epoch)
    groups = {}
    for part in partitions:
        key = (part["exchange"], part["market_type"], part["symbol"],
               part["dataset"], part["timeframe_ns"])
        groups.setdefault(key, []).append(part)
    if set(groups) != set(expected_ranges):
        raise PartitionContractError("Missing or unexpected market partitions")
    for key, expected in expected_ranges.items():
        if (type(expected) is not tuple or len(expected) != 2
                or any(type(v) is not int or v < 0 for v in expected)):
            raise PartitionContractError("Invalid expected range")
        start, end = expected
        step = key[-1]
        if start > end or start % step or end % step:
            raise PartitionContractError("Misaligned expected range")
        cursor = start
        for part in sorted(groups[key], key=lambda p: p["first_event_ns"]):
            first, last = part["first_event_ns"], part["last_event_ns"]
            if first != cursor or first % step or last % step or (last-first) % step:
                raise PartitionContractError("Missing, overlapping or misaligned interval")
            expected_count = (last-first)//step + 1
            if part["row_count"] != expected_count:
                raise PartitionContractError("Row count disagrees with regular interval")
            cursor = last + step
        if cursor != end + step:
            raise PartitionContractError("Incomplete final range")
