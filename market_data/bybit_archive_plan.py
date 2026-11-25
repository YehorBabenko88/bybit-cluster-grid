"""Deterministic daily Bybit public-trade archive planning.

Planning never equates a missing HTTP file with a verified empty trading day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re


_SYMBOL = re.compile(r"^[A-Z0-9-]{2,40}$")


@dataclass(frozen=True)
class ArchiveDay:
    symbol: str
    day: date
    market: str
    url: str


def archive_url(symbol: str, day: date, market: str = "linear") -> str:
    if type(day) is not date:
        raise ValueError("archive day must be a calendar date")
    if type(symbol) is not str or not _SYMBOL.fullmatch(symbol):
        raise ValueError("invalid Bybit symbol")
    if market not in ("linear", "inverse", "spot"):
        raise ValueError("unsupported market")
    if market == "spot":
        return f"https://public.bybit.com/spot/{symbol}/{symbol}_{day.isoformat()}.csv.gz"
    return f"https://public.bybit.com/trading/{symbol}/{symbol}{day.isoformat()}.csv.gz"


def plan_archive_days(symbol: str, start: date, end: date, *,
                      market: str = "linear", today: date | None = None,
                      max_days: int = 3660) -> list[ArchiveDay]:
    """Plan inclusive start, exclusive end, excluding today's unfinished file."""
    today = date.today() if today is None else today
    if (any(type(value) is not date for value in (start, end, today))
            or type(max_days) is not int or not 1 <= max_days <= 3660):
        raise ValueError("bounded calendar-day archive plan required")
    if start >= end or end > today:
        raise ValueError("interval must be nonempty and end no later than today")
    days = (end - start).days
    if days > max_days or max_days < 1:
        raise ValueError("archive plan exceeds configured day budget")
    return [ArchiveDay(symbol, start + timedelta(days=i), market,
                       archive_url(symbol, start + timedelta(days=i), market))
            for i in range(days)]
