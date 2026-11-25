"""Validate trade timestamps against an explicitly requested UTC archive day.

This is a content-boundary check, not an independent proof that every trade
from that day was published by the exchange.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .bybit_archive_audit import ArchiveAudit
from .timestamp_codec import epoch_milliseconds_from_utc


@dataclass(frozen=True)
class DayBoundary:
    day: date
    start_ms: int
    end_ms: int


def utc_day_boundary(day: date) -> DayBoundary:
    if not isinstance(day, date) or isinstance(day, datetime):
        raise TypeError("day must be a date")
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return DayBoundary(day, epoch_milliseconds_from_utc(start),
                       epoch_milliseconds_from_utc(end))


def validate_day_audit(audit: ArchiveAudit, day: date) -> None:
    """Reject archives whose observed endpoints lie outside their UTC day."""
    boundary = utc_day_boundary(day)
    if not audit.valid or audit.rows < 1:
        raise ValueError("archive content has not passed validation")
    if audit.first_ms is None or audit.last_ms is None:
        raise ValueError("archive has no verified timestamp endpoints")
    if not (boundary.start_ms <= audit.first_ms <= audit.last_ms < boundary.end_ms):
        raise ValueError("archive timestamps fall outside the requested UTC day")
