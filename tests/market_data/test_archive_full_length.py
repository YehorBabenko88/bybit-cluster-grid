# Source Meta82 test_archive_full_length.py; canonical import transfer.
"""Regression coverage for full archive response length validation."""
import pytest

from market_data.bybit_archive_download import download_archive

URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


class Response:
    status = 200

    def __init__(self, payload, declared):
        self.content_length = declared
        self.payload = payload
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    async def iter_chunked(self, size):
        yield self.payload


class Session:
    def __init__(self, response):
        self.response = response

    def get(self, url, *, allow_redirects):
        assert url == URL and not allow_redirects
        return self.response


@pytest.mark.asyncio
async def test_reject_short_full_response_without_replacing_destination(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    destination.write_bytes(b"verified-old")
    with pytest.raises(ValueError, match="length mismatch"):
        await download_archive(Session(Response(b"abc", 6)), URL, destination)
    assert destination.read_bytes() == b"verified-old"
    assert not destination.with_name(destination.name + ".partial").exists()


@pytest.mark.asyncio
async def test_accept_exact_full_response(tmp_path):
    destination = tmp_path / "archive.csv.gz"
    await download_archive(Session(Response(b"abcdef", 6)), URL, destination)
    assert destination.read_bytes() == b"abcdef"
