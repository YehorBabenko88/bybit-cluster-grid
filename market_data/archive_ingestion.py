"""Bounded archive download + validation, with durable local audit receipts.

A successful receipt confirms parsing of the downloaded file, never completeness
of historical market trades. The receipt is tied to file bytes via SHA-256.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from .archive_file_lock import async_archive_file_lock
from .bybit_archive_audit import audit_trade_gzip
from .archive_day_boundary import validate_day_audit, utc_day_boundary
from .bybit_archive_download import download_archive, validate_archive_url
from .archive_resumable_download import download_resumable
from .history_parallel import bounded_map


@dataclass(frozen=True)
class ArchiveReceipt:
    url: str
    sha256: str
    bytes: int
    rows: int
    first_ms: int | None
    last_ms: int | None
    valid: bool
    complete: bool = False
    day: str | None = None


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _receipt_path(path: Path) -> Path:
    return path.with_name(path.name + ".audit.json")


def _load_receipt(path: Path, url: str, day: date | None = None, max_bytes: int = 2_000_000_000) -> ArchiveReceipt | None:
    try:
        with _receipt_path(path).open("rb") as stream:
            raw = stream.read(16385)
        if len(raw)>16384:return None
        data = json.loads(raw.decode("utf-8"))
        receipt = ArchiveReceipt(**data)
        if (receipt.url == url and receipt.day == (day.isoformat() if day else None)
                and receipt.valid is True and receipt.complete is False
                and type(receipt.rows) is int and receipt.rows > 0
                and type(receipt.bytes) is int and receipt.bytes > 0 and receipt.bytes <= max_bytes
                and isinstance(receipt.sha256, str) and len(receipt.sha256) == 64
                and all(character in "0123456789abcdef" for character in receipt.sha256)
                and type(receipt.first_ms) is int and 0 <= receipt.first_ms < 253402300800000
                and type(receipt.last_ms) is int and receipt.last_ms >= receipt.first_ms
                and receipt.last_ms < 253402300800000
                and (day is None or (utc_day_boundary(day).start_ms <= receipt.first_ms
                                     and receipt.last_ms < utc_day_boundary(day).end_ms))
                and path.stat().st_size == receipt.bytes
                and _digest(path) == receipt.sha256):
            audit = audit_trade_gzip(path)
            if (audit.valid is True and audit.complete is False
                    and (audit.rows,audit.first_ms,audit.last_ms)==(receipt.rows,receipt.first_ms,receipt.last_ms)
                    and path.stat().st_size==receipt.bytes and _digest(path)==receipt.sha256):
                return receipt
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def _write_receipt(path: Path, receipt: ArchiveReceipt) -> None:
    dest = _receipt_path(path)
    temporary = dest.with_name(dest.name + ".partial")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(asdict(receipt), stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)


async def _to_thread_join_on_cancel(func, /, *args, **kwargs):
    """Do not release the archive lock while a cancelled thread still runs.

    Shielding prevents cancellation from cancelling the task wrapper; after a
    cancellation request, wait for the actual worker to finish before the
    caller's async lock context is allowed to exit.
    """
    worker = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # A second cancellation during cleanup must not release the lock
        # while the worker is still reading or publishing archive bytes.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                # The original cancellation remains authoritative.
                break
        raise


async def acquire_archive(session, url: str, path: str | Path, *,
                          max_bytes: int = 2_000_000_000,
                          day: date | None = None,
                          resumable: bool = False) -> ArchiveReceipt:
    validate_archive_url(url)
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2_000_000_000:
        raise ValueError("max_bytes must be a positive integer")
    if day is not None:
        utc_day_boundary(day)  # validate before any filesystem or network effects
    path = Path(path)
    async with async_archive_file_lock(path):
        if path.is_file():
            cached = await _to_thread_join_on_cancel(_load_receipt, path, url, day, max_bytes)
            if cached is not None:
                return cached
        transport = download_resumable if resumable else download_archive
        await transport(session, url, path, max_bytes=max_bytes)
        try:
            audit = await _to_thread_join_on_cancel(audit_trade_gzip, path)
            if not audit.valid:
                raise ValueError(f"archive rejected: {audit.reason}")
            if day is not None:
                validate_day_audit(audit, day)
        except Exception:
            # Never leave a stale receipt advertising bytes replaced by a
            # failed validation. The next attempt must download and audit.
            await _to_thread_join_on_cancel(_receipt_path(path).unlink, missing_ok=True)
            raise
        size, digest = await _to_thread_join_on_cancel(lambda: (path.stat().st_size, _digest(path)))
        receipt = ArchiveReceipt(url, digest, size, audit.rows, audit.first_ms,
                                 audit.last_ms, True, False,
                                 day.isoformat() if day else None)
        await _to_thread_join_on_cancel(_write_receipt, path, receipt)
        return receipt


async def acquire_many(archives: list[tuple[str, str | Path]], *,
                       concurrency: int = 4, max_bytes: int = 2_000_000_000,
                       resumable: bool = False):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2_000_000_000:
        raise ValueError("max_bytes must be a positive integer")
    if type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ValueError("concurrency must be a positive integer")
    # Two workers must never write the same .partial or audit receipt path.
    # Resolve paths before opening network sessions; reject collisions early.
    destinations = [str(Path(path).resolve()) for _, path in archives]
    if len(destinations) != len(set(destinations)):
        raise ValueError("duplicate archive destination in batch")
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=120)
    connector = aiohttp.TCPConnector(limit=max(1, concurrency))
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async def worker(entry):
            return await acquire_archive(session, entry[0], entry[1],
                                         max_bytes=max_bytes, resumable=resumable)
        return await bounded_map(archives, worker, concurrency=concurrency)
