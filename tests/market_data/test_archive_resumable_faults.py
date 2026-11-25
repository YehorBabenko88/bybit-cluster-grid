# Source Meta82 test_archive_resumable_faults.py; canonical import transfer.
"""Fault injection for resumable transport without external networking."""
import asyncio

import pytest

from market_data.archive_partial_state import partial_paths, read_partial
from market_data.archive_resumable_download import download_resumable

URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


class BrokenStream:
    def __init__(self, chunks, failure=None):
        self.chunks = chunks
        self.failure = failure

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk
        if self.failure is not None:
            raise self.failure


class Response:
    def __init__(self, status, chunks, headers, failure=None):
        self.status = status
        self.headers = headers
        self.content_length = int(headers["Content-Length"])
        self.content = BrokenStream(chunks, failure)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise ValueError("HTTP error")


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, *, headers, allow_redirects):
        assert url == URL and not allow_redirects
        self.requests.append(headers)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_connection_error_checkpoints_and_resumes(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    session = Session([
        Response(200, [b"abc"], {"ETag": '"v1"', "Content-Length": "6"},
                 ConnectionResetError("socket closed")),
        Response(206, [b"def"], {"ETag": '"v1"', "Content-Length": "3",
                                  "Content-Range": "bytes 3-5/6"}),
    ])
    with pytest.raises(ConnectionResetError):
        await download_resumable(session, URL, destination)
    assert read_partial(destination, URL).offset == 3
    await download_resumable(session, URL, destination)
    assert destination.read_bytes() == b"abcdef"
    assert session.requests[1]["Range"] == "bytes=3-"


@pytest.mark.asyncio
async def test_cancellation_checkpoints_without_suppressing_cancel(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    session = Session([
        Response(200, [b"abc"], {"ETag": '"v1"', "Content-Length": "6"},
                 asyncio.CancelledError()),
    ])
    with pytest.raises(asyncio.CancelledError):
        await download_resumable(session, URL, destination)
    assert read_partial(destination, URL).offset == 3


@pytest.mark.asyncio
async def test_wrong_range_does_not_append_partial(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    session = Session([
        Response(200, [b"abc"], {"ETag": '"v1"', "Content-Length": "6"}),
        Response(206, [b"def"], {"ETag": '"v1"', "Content-Length": "3",
                                  "Content-Range": "bytes 2-4/6"}),
    ])
    with pytest.raises(ValueError, match="partial retained"):
        await download_resumable(session, URL, destination)
    partial, _ = partial_paths(destination)
    assert partial.read_bytes() == b"abc"
    with pytest.raises(ValueError, match="range"):
        await download_resumable(session, URL, destination)
    assert partial.read_bytes() == b"abc"


@pytest.mark.asyncio
async def test_initial_response_requires_explicit_content_length(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    response = Response(200, [b"abcdef"], {"ETag": '"v1"', "Content-Length": "6"})
    del response.headers["Content-Length"]
    with pytest.raises(ValueError, match="explicit Content-Length"):
        await download_resumable(Session([response]), URL, destination)
    assert not destination.exists()


@pytest.mark.asyncio
async def test_sidecar_cleanup_failure_does_not_hide_published_archive(tmp_path, monkeypatch):
    from pathlib import Path

    destination = tmp_path / "archive.csv.gz"
    sidecar = partial_paths(destination)[1]
    original_unlink = Path.unlink

    def fail_sidecar_unlink(self, *args, **kwargs):
        # Initial discard_partial() runs before the transfer. Only inject
        # the failure after os.replace() has published the destination.
        if self == sidecar and destination.exists():
            raise PermissionError("sidecar temporarily locked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_sidecar_unlink)
    session = Session([
        Response(200, [b"abcdef"], {"ETag": '"v1"', "Content-Length": "6"}),
    ])
    result = await download_resumable(session, URL, destination)
    assert result == destination
    assert destination.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_fsync_failure_preserves_cancellation_without_checkpoint(tmp_path, monkeypatch):
    import os

    destination = tmp_path / "archive.csv.gz"
    session = Session([
        Response(200, [b"abc"], {"ETag": '"v1"', "Content-Length": "6"},
                 asyncio.CancelledError()),
    ])

    def fail_fsync(fd):
        raise OSError("disk synchronization failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(asyncio.CancelledError):
        await download_resumable(session, URL, destination)
    assert read_partial(destination, URL) is None
    assert not destination.exists()


@pytest.mark.asyncio
async def test_fsync_failure_without_transport_error_propagates(tmp_path, monkeypatch):
    import os

    destination = tmp_path / "archive.csv.gz"
    session = Session([
        Response(200, [b"abcdef"], {"ETag": '"v1"', "Content-Length": "6"}),
    ])

    def fail_fsync(fd):
        raise OSError("disk synchronization failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="disk synchronization failed"):
        await download_resumable(session, URL, destination)
    assert not destination.exists()
