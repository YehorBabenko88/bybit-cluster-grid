# Source Meta82 test_archive_resumable_download.py; canonical import transfer.
import pytest

from market_data.archive_resumable_download import download_resumable
from market_data.archive_partial_state import partial_paths

URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


class Response:
    def __init__(self, status, payload, headers):
        self.status = status
        self.payload = payload
        self.headers = headers
        self.content_length = int(headers["Content-Length"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise ValueError("HTTP error")

    @property
    def content(self):
        return self

    async def iter_chunked(self, size):
        yield self.payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = []

    def get(self, url, *, headers, allow_redirects):
        assert url == URL and not allow_redirects
        self.headers.append(headers)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_resumable_download_preserves_and_resumes(tmp_path):
    path = tmp_path / "trades.csv.gz"
    session = Session([
        Response(200, b"abc", {"ETag": '"v1"', "Content-Length": "6"}),
        Response(206, b"def", {"ETag": '"v1"', "Content-Length": "3",
                               "Content-Range": "bytes 3-5/6"}),
    ])
    with pytest.raises(ValueError, match="partial retained"):
        await download_resumable(session, URL, path)
    partial, sidecar = partial_paths(path)
    assert partial.read_bytes() == b"abc" and sidecar.exists()
    await download_resumable(session, URL, path)
    assert path.read_bytes() == b"abcdef"
    assert not partial.exists() and not sidecar.exists()
    assert session.headers[1]["Range"] == "bytes=3-"
    assert session.headers[1]["If-Range"] == '"v1"'


@pytest.mark.asyncio
async def test_server_ignores_range_without_corrupting_existing_file(tmp_path):
    path = tmp_path / "trades.csv.gz"
    path.write_bytes(b"existing")
    session = Session([
        Response(200, b"abc", {"ETag": '"v1"', "Content-Length": "6"}),
        Response(200, b"abcdef", {"ETag": '"v2"', "Content-Length": "6"}),
    ])
    with pytest.raises(ValueError, match="partial retained"):
        await download_resumable(session, URL, path)
    with pytest.raises(ValueError, match="partial content"):
        await download_resumable(session, URL, path)
    assert path.read_bytes() == b"existing"
