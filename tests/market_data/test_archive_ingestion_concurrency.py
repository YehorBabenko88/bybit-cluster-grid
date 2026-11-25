# Original Meta82 test_archive_ingestion_concurrency.py; canonical import transfer.
import pytest

from market_data.archive_ingestion import acquire_many


@pytest.mark.asyncio
async def test_parallel_ingestion_rejects_duplicate_destinations(tmp_path):
    path = tmp_path / "BTCUSDT.csv.gz"
    url = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"
    with pytest.raises(ValueError, match="duplicate archive destination"):
        await acquire_many([(url, path), (url, path)])
    assert not path.exists()
    assert not (tmp_path / "BTCUSDT.csv.gz.partial").exists()


@pytest.mark.asyncio
async def test_parallel_ingestion_detects_alias_destinations(tmp_path):
    path = tmp_path / "BTCUSDT.csv.gz"
    alias = tmp_path / "sub" / ".." / "BTCUSDT.csv.gz"
    url = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"
    with pytest.raises(ValueError, match="duplicate archive destination"):
        await acquire_many([(url, path), (url, alias)])
