"""Streaming downloader for public daily archives.

Only HTTPS and the pinned Bybit archive host are allowed. Files are written
to temporary paths and promoted atomically after successful transfer.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import os
from .archive_file_lock import guard_archive_destination
from urllib.parse import urlparse, unquote

from .history_parallel import bounded_map


def validate_archive_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "public.bybit.com" or parsed.port is not None:
        raise ValueError("untrusted archive URL")
    if not parsed.path.startswith(("/trading/", "/spot/")) or not parsed.path.endswith(".csv.gz"):
        raise ValueError("unsupported archive path")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("archive URL must not contain credentials or query")
    # Reject encoded separators, traversal and ambiguous URL normalization.
    # Only the expected archive directory / symbol / filename shape is allowed.
    if parsed.path != unquote(parsed.path) or "\\\\" in parsed.path:
        raise ValueError("encoded or ambiguous archive path")
    parts = parsed.path.split("/")
    if len(parts) != 4 or parts[0] or parts[1] not in ("trading", "spot"):
        raise ValueError("invalid archive directory structure")
    symbol, filename = parts[2], parts[3]
    if not symbol or not symbol.isascii() or not symbol.isalnum():
        raise ValueError("invalid archive symbol")
    if not filename.startswith(symbol) or not filename.endswith(".csv.gz"):
        raise ValueError("archive filename does not match symbol")
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-" for ch in filename):
        raise ValueError("invalid archive filename")


async def download_archive(session, url: str, destination: str | Path,
                           *, max_bytes: int = 2_000_000_000, chunk_bytes: int = 1 << 20) -> Path:
    validate_archive_url(url)
    if (type(max_bytes) is not int or not 1 <= max_bytes <= 2_000_000_000
            or type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 1_048_576):
        raise ValueError("invalid download limits")
    destination = guard_archive_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    try:
        async with session.get(url, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status != 200:
                raise ValueError(f"unexpected archive response {response.status}")
            declared = response.content_length
            if declared is not None and declared > max_bytes:
                raise ValueError("archive exceeds maximum allowed bytes")
            total = 0
            with partial.open("wb") as output:
                async for chunk in response.content.iter_chunked(chunk_bytes):
                    if total + len(chunk) > max_bytes:
                        raise ValueError("archive exceeds maximum allowed bytes")
                    output.write(chunk)
                    total += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if declared is not None and total != declared:
                raise ValueError("archive response length mismatch")
        os.replace(partial, destination)
        return destination
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


async def download_many(archives: list[tuple[str, str | Path]], *,
                        concurrency: int = 4, max_bytes: int = 2_000_000_000):
    import aiohttp  # optional download-only dependency; core app and tests can import without it
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=120)
    connector = aiohttp.TCPConnector(limit=max(1, concurrency))
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async def worker(entry):
            url, destination = entry
            return await download_archive(session, url, destination, max_bytes=max_bytes)
        return await bounded_map(archives, worker, concurrency=concurrency)
