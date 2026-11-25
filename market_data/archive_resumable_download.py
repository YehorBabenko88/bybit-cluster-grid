"""Resumable streaming archive transport with conservative HTTP validation.

Requires a strong ETag and Content-Length for resumable transfers.
When these are absent, callers should use the ordinary atomic downloader.
"""
from __future__ import annotations

from pathlib import Path
import os
from .archive_file_lock import guard_archive_destination

from .archive_partial_state import (
    discard_partial, partial_paths, read_partial, save_partial,
)
from .archive_resume import ResumeState, resume_headers, strong_etag, validate_partial_response
from .bybit_archive_download import validate_archive_url


async def download_resumable(session, url: str, destination: str | Path, *,
                             max_bytes: int = 2_000_000_000,
                             chunk_bytes: int = 1 << 20) -> Path:
    validate_archive_url(url)
    if (type(max_bytes) is not int or not 1 <= max_bytes <= 2_000_000_000
            or type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 1_048_576):
        raise ValueError("invalid download limits")
    destination = guard_archive_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial, sidecar = partial_paths(destination)
    state = read_partial(destination, url, max_bytes=max_bytes)
    if state is None:
        discard_partial(destination)
    headers = resume_headers(state) if state is not None else {
        "Accept-Encoding": "identity"
    }
    async with session.get(url, headers=headers, allow_redirects=False) as response:
        response.raise_for_status()
        if state is not None:
            expected = validate_partial_response(response.status, response.headers, state)
            etag = state.etag
            total = state.total_bytes
            offset = state.offset
        else:
            if response.status != 200:
                raise ValueError("expected full archive response")
            etag = response.headers.get("ETag")
            total = response.content_length
            declared = response.headers.get("Content-Length")
            if declared is None:
                raise ValueError("resumable archive requires explicit Content-Length")
            try:
                header_total = int(declared)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid archive Content-Length") from exc
            if header_total != total:
                raise ValueError("archive Content-Length disagrees with response")
            if not strong_etag(etag) or total is None or total < 1:
                raise ValueError("resumable archive requires strong ETag and length")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("compressed HTTP transfer encoding not supported")
            if total > max_bytes:
                raise ValueError("archive exceeds maximum allowed bytes")
            offset = 0
            expected = total
        if total > max_bytes:
            raise ValueError("archive exceeds maximum allowed bytes")
        transferred = 0
        transfer_error = None
        durable = True
        with partial.open("ab" if state is not None else "wb") as stream:
            try:
                async for chunk in response.content.iter_chunked(chunk_bytes):
                    if transferred + len(chunk) > expected:
                        raise ValueError("archive response exceeds declared range")
                    stream.write(chunk)
                    transferred += len(chunk)
            except BaseException as exc:
                # Preserve cancellation semantics after durable checkpointing.
                transfer_error = exc
            finally:
                try:
                    stream.flush()
                    os.fsync(stream.fileno())
                except OSError:
                    durable = False
                    if transfer_error is None:
                        raise
                    # The original cancellation/transport failure takes
                    # precedence. Without a durable checkpoint, the next
                    # invocation discards the untrusted partial bytes.
        if transfer_error is not None:
            # Never let checkpoint I/O replace the original cancellation or
            # transport failure; the next run rejects unsaved partial bytes.
            if durable and 0 < transferred < expected:
                try:
                    save_partial(destination, url, ResumeState(offset + transferred, etag, total))
                except OSError:
                    pass
            raise transfer_error
        if transferred != expected:
            # Preserve only bytes that were actually flushed to disk.
            if transferred > 0:
                save_partial(destination, url, ResumeState(offset + transferred, etag, total))
            raise ValueError("incomplete archive response; partial retained")
    if partial.stat().st_size != total:
        raise ValueError("archive size mismatch")
    os.replace(partial, destination)
    # The completed destination is authoritative. Removing an obsolete
    # sidecar is best effort: a cleanup failure must not report a failed
    # download after the archive has already been atomically published.
    try:
        sidecar.unlink(missing_ok=True)
    except OSError:
        pass
    return destination
