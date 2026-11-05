"""Offline download-to-parser composition; no sockets or external services."""
import asyncio
import gzip
import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from grid import archive_download
from grid.archive_stream_parser import iter_archive_rows, iter_minute_aggregates

NODES = ('LS5', 'PC1', 'PC2', 'PC3', 'PC4', 'LS7')
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT',
           'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT')
CSV = b'timestamp,side,price,size,trade_id\n1767225600,Buy,100,2,a\n'


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    async def iter_chunked(self, size):
        for start in range(0, len(self.payload), min(size, 17)):
            yield self.payload[start:start + min(size, 17)]


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, url, **kwargs):
        assert url.startswith('https://fixture.invalid/')
        return FakeResponse(self.payload)


@pytest.mark.parametrize('node,symbol', [(NODES[i % 6], s) for i, s in enumerate(SYMBOLS)])
def test_downloaded_gzip_parses_without_filename_suffix(tmp_path, monkeypatch, node, symbol):
    payload = gzip.compress(CSV, mtime=0)
    monkeypatch.setattr(archive_download.aiohttp, 'ClientSession', lambda: FakeSession(payload))
    root = tmp_path / node
    result = asyncio.run(archive_download.download_verified(
        'https://fixture.invalid/' + symbol + '.csv.gz', str(root),
        expected_sha256=hashlib.sha256(payload).hexdigest(), expected_bytes=len(payload)))
    assert result['bytes'] == len(payload)
    assert result['sha256'] == hashlib.sha256(payload).hexdigest()
    assert not result['path'].endswith('.gz')
    rows = list(iter_minute_aggregates(result['path'], symbol, .5))
    assert len(rows) == 1
    assert rows[0]['trade_count'] == 1 and rows[0]['buy_volume'] == 2
    assert Path(result['path']).read_bytes() == payload


@pytest.mark.parametrize('kind', ['truncated', 'crc'])
def test_suffixless_gzip_corruption_is_rejected(tmp_path, kind):
    payload = gzip.compress(CSV, mtime=0)
    payload = payload[:-4] if kind == 'truncated' else payload[:-8] + bytes([payload[-8] ^ 1]) + payload[-7:]
    path = tmp_path / 'archive'
    path.write_bytes(payload)
    with pytest.raises((EOFError, OSError)):
        list(iter_archive_rows(str(path)))


def test_suffixless_zip_preserves_single_csv_rule(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('trades.csv', CSV)
    path = tmp_path / 'archive'
    path.write_bytes(data.getvalue())
    assert list(iter_archive_rows(str(path)))[0]['trade_id'] == 'a'
    with zipfile.ZipFile(path, 'a') as z:
        z.writestr('second.csv', CSV)
    with pytest.raises(ValueError, match='exactly one CSV'):
        list(iter_archive_rows(str(path)))


def test_plain_csv_and_invalid_declared_gzip(tmp_path):
    path = tmp_path / 'plain.csv'
    path.write_bytes(CSV)
    assert list(iter_archive_rows(str(path)))[0]['trade_id'] == 'a'
    declared = tmp_path / 'invalid.gz'
    declared.write_bytes(CSV)
    with pytest.raises(OSError):
        list(iter_archive_rows(str(declared)))
