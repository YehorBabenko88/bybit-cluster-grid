# Original Meta82 test_archive_ingestion_resume.py; canonical import transfer.
import csv
import gzip

import pytest

from market_data.archive_ingestion import acquire_archive

URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


@pytest.mark.asyncio
async def test_opt_in_resume_uses_audited_ingestion(tmp_path, monkeypatch):
    from market_data import archive_ingestion
    path = tmp_path / "trades.csv.gz"
    calls = []

    async def resumable(session, url, destination, **kwargs):
        calls.append(("resume", url))
        with gzip.open(destination, "wt", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["trdMatchID", "timestamp", "price", "size", "side"])
            writer.writeheader()
            writer.writerow({"trdMatchID": "id1", "timestamp": "1735689600", "price": "100", "size": "1", "side": "Buy"})
        return destination

    async def ordinary(*args, **kwargs):
        raise AssertionError("ordinary transport should not be used")

    monkeypatch.setattr(archive_ingestion, "download_resumable", resumable)
    monkeypatch.setattr(archive_ingestion, "download_archive", ordinary)
    receipt = await acquire_archive(object(), URL, path, resumable=True)
    assert receipt.valid and not receipt.complete and receipt.rows == 1
    assert calls == [("resume", URL)]
    assert await acquire_archive(object(), URL, path, resumable=True) == receipt
    assert len(calls) == 1
