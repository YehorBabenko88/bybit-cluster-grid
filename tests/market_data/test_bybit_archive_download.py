# Source Meta82 test_bybit_archive_download.py; canonical import transfer.
import pytest

from market_data.bybit_archive_download import validate_archive_url, download_archive


def test_archive_url_allowlist():
    validate_archive_url("https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz")
    for url in (
        "http://public.bybit.com/trading/BTCUSDT/a.csv.gz",
        "https://evil.example/trading/BTCUSDT/a.csv.gz",
        "https://public.bybit.com.evil.example/trading/a.csv.gz",
        "https://public.bybit.com/trading/BTCUSDT/a.zip",
        "https://public.bybit.com/trading/a.csv.gz?redirect=1",
    ):
        with pytest.raises(ValueError):
            validate_archive_url(url)


@pytest.mark.asyncio
async def test_stream_download_and_atomic_commit(tmp_path):
    class Response:
        status = 200
        content_length = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        @property
        def content(self):
            return self

        async def iter_chunked(self, chunk_bytes):
            yield b"abc"
            yield b"def"

    class Session:
        def get(self, *args, **kwargs):
            assert kwargs["allow_redirects"] is False
            return Response()

    path = tmp_path / "daily.csv.gz"
    await download_archive(Session(), "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz", path)
    assert path.read_bytes() == b"abcdef"
    assert not (tmp_path / "daily.csv.gz.partial").exists()


@pytest.mark.asyncio
async def test_download_limit_preserves_existing_file(tmp_path):
    class Response:
        status = 200
        content_length = 100

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    path = tmp_path / "daily.csv.gz"
    path.write_bytes(b"old")
    with pytest.raises(ValueError, match="maximum"):
        await download_archive(Session(), "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz",
                               path, max_bytes=10)
    assert path.read_bytes() == b"old"
    assert not (tmp_path / "daily.csv.gz.partial").exists()
