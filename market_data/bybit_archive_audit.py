"""Stream-validation of downloaded Bybit public trade archives.

A valid gzip/CSV is not proof of complete market history; coverage remains
unverified until an independent completeness source is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import csv
import gzip
import io
from pathlib import Path
from market_math import decimal_epoch_units
from .public_trades import _decimal


@dataclass(frozen=True)
class ArchiveAudit:
    rows: int
    first_ms: int | None
    last_ms: int | None
    valid: bool
    complete: bool
    reason: str


def audit_trade_gzip(path: str | Path, *, max_rows: int = 50_000_000,
                     max_uncompressed_bytes: int = 8_000_000_000) -> ArchiveAudit:
    if (type(max_rows) is not int or max_rows <= 0
            or type(max_uncompressed_bytes) is not int or max_uncompressed_bytes <= 0):
        raise ValueError("audit budgets must be positive integers")
    rows = 0
    first = last = None
    previous_timestamp = None
    try:
        with gzip.open(path, "rb") as compressed:
            stream = io.TextIOWrapper(_LimitedReader(compressed, max_uncompressed_bytes),
                                      encoding="utf-8-sig", newline="")
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames or []
            fields = set(header)
            if not {"trdMatchID", "timestamp", "price", "size", "side"}.issubset(fields):
                return ArchiveAudit(0, None, None, False, False, "required columns missing")
            if len(header) != len(fields):
                return ArchiveAudit(0, None, None, False, False, "duplicate CSV columns")
            for record in reader:
                rows += 1
                if rows > max_rows:
                    return ArchiveAudit(rows, first, last, False, False, "row budget exceeded")
                try:
                    if None in record or any(value is None for value in record.values()):
                        raise ValueError("malformed CSV field count")
                    if not record["trdMatchID"].strip():
                        raise ValueError("missing trade ID")
                    if record["side"] not in ("Buy", "Sell"):
                        raise ValueError("invalid trade side")
                    timestamp_ms = decimal_epoch_units(record["timestamp"], 3)
                    raw_ts = Decimal(record["timestamp"])
                    price = _decimal(record["price"])
                    size = _decimal(record["size"])
                    if not raw_ts.is_finite() or not price.is_finite() or not size.is_finite():
                        raise ValueError("nonfinite numeric value")
                    if not (0 <= raw_ts < Decimal("253402300800")) or price <= 0 or size <= 0:
                        raise ValueError("invalid trade values")
                    if previous_timestamp is not None and raw_ts < previous_timestamp:
                        raise ValueError("out-of-order trades")
                except (ValueError, TypeError, InvalidOperation, KeyError) as exc:
                    return ArchiveAudit(rows, first, last, False, False, f"invalid row: {exc}")
                if first is None:
                    first = timestamp_ms
                last = timestamp_ms
                previous_timestamp = raw_ts
    except (OSError, EOFError, UnicodeError, csv.Error, ValueError) as exc:
        return ArchiveAudit(rows, first, last, False, False, f"corrupt archive: {exc}")
    if not rows:
        return ArchiveAudit(0, None, None, False, False, "empty archive")
    return ArchiveAudit(rows, first, last, True, False,
                        "parsed successfully; completeness not independently verified")


class _LimitedReader(io.RawIOBase):
    """Cap decompressed bytes, including the CSV header and long lines."""

    def __init__(self, source, limit: int):
        self.source = source
        self.remaining = limit

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.remaining == 0:
            if self.source.read(1):
                raise ValueError("decompressed archive byte budget exceeded")
            return 0
        chunk = self.source.read(min(len(buffer), self.remaining + 1))
        if len(chunk) > self.remaining:
            raise ValueError("decompressed archive byte budget exceeded")
        buffer[:len(chunk)] = chunk
        self.remaining -= len(chunk)
        return len(chunk)
