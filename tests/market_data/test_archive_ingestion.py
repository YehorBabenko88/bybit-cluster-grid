# Original Meta82 test_archive_ingestion.py; canonical import transfer.
import csv
import gzip
import json

import pytest

from market_data.archive_ingestion import acquire_archive


URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


def make_gzip(path):
    import io

    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["trdMatchID", "timestamp", "price", "size", "side"])
                writer.writeheader()
                writer.writerow({"trdMatchID": "id1", "timestamp": "1735689600", "price": "100", "size": "2", "side": "Buy"})


@pytest.mark.asyncio
async def test_cached_receipt_skips_network_and_detects_tampering(tmp_path, monkeypatch):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    first = await acquire_archive(object(), URL, path)
    assert first.valid and not first.complete and first.rows == 1
    assert len(calls) == 1
    second = await acquire_archive(object(), URL, path)
    assert second == first and len(calls) == 1
    path.write_bytes(b"tampered")
    third = await acquire_archive(object(), URL, path)
    assert third == first and len(calls) == 2


@pytest.mark.asyncio
async def test_invalid_archive_never_receives_audit_receipt(tmp_path, monkeypatch):
    from market_data import archive_ingestion
    path = tmp_path / "bad.csv.gz"

    async def fake_download(session, url, dest, **kwargs):
        dest.write_bytes(b"invalid gzip")
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    with pytest.raises(ValueError, match="archive rejected"):
        await acquire_archive(object(), URL, path)
    assert not (tmp_path / "bad.csv.gz.audit.json").exists()


@pytest.mark.asyncio
async def test_failed_replacement_removes_stale_receipt(tmp_path, monkeypatch):
    from market_data import archive_ingestion

    path = tmp_path / "archive.csv.gz"
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            make_gzip(dest)
        else:
            dest.write_bytes(b"not a gzip archive")
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    assert receipt_path.exists()
    # Change the existing file so the cached receipt is no longer trusted.
    path.write_bytes(b"changed after audit")
    with pytest.raises(ValueError, match="archive rejected"):
        await acquire_archive(object(), URL, path)
    assert len(calls) == 2
    assert not receipt_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_rows", [0, -1, True])
async def test_invalid_cached_receipt_row_count_forces_reaudit(tmp_path, monkeypatch, bad_rows):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["rows"] = bad_rows
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.rows == 1
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "bad_value"), [
    ("bytes", 0),
    ("bytes", -1),
    ("bytes", True),
    ("sha256", "not-a-sha256"),
])
async def test_invalid_cached_receipt_metadata_forces_reaudit(tmp_path, monkeypatch, field, bad_value):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = bad_value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.valid and result.rows == 1
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "bad_value"), [
    ("first_ms", None),
    ("first_ms", True),
    ("first_ms", -1),
    ("last_ms", None),
    ("last_ms", False),
    ("last_ms", -1),
    ("last_ms", 253402300800000),
    ("first_ms", 253402300800000),
])
async def test_invalid_cached_receipt_time_bounds_force_reaudit(tmp_path, monkeypatch, field, bad_value):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = bad_value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.valid and result.first_ms <= result.last_ms
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cached_receipt_cannot_bypass_smaller_byte_budget(tmp_path, monkeypatch):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(kwargs["max_bytes"])
        if path.is_file() and path.stat().st_size > kwargs["max_bytes"]:
            raise ValueError("archive exceeds byte budget")
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    assert path.stat().st_size > 1
    with pytest.raises(ValueError, match="byte budget"):
        await acquire_archive(object(), URL, path, max_bytes=1)
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "bad_value"), [
    ("valid", 1),
    ("valid", "true"),
    ("complete", 0),
    ("complete", None),
])
async def test_nonboolean_cached_receipt_flags_force_reaudit(tmp_path, monkeypatch, field, bad_value):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    make_gzip(path)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt[field] = bad_value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.valid is True and result.complete is False
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_budget", [0, -1, True, False, 1.5, "100"])
async def test_invalid_max_bytes_rejected_before_download(tmp_path, monkeypatch, bad_budget):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"

    async def unexpected_download(*args, **kwargs):
        pytest.fail("invalid budget must not reach network")

    monkeypatch.setattr(archive_ingestion, "download_archive", unexpected_download)
    with pytest.raises(ValueError, match="max_bytes must be a positive integer"):
        await acquire_archive(object(), URL, path, max_bytes=bad_budget)
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_budget", [0, -1, True, 1.5, "100"])
async def test_batch_rejects_invalid_budget_before_session_creation(bad_budget):
    from market_data.archive_ingestion import acquire_many

    with pytest.raises(ValueError, match="max_bytes must be a positive integer"):
        await acquire_many([], max_bytes=bad_budget)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_concurrency", [0, -1, True, False, 1.5, "4"])
async def test_batch_rejects_invalid_concurrency_before_session_creation(bad_concurrency):
    from market_data.archive_ingestion import acquire_many

    with pytest.raises(ValueError, match="concurrency must be a positive integer"):
        await acquire_many([], concurrency=bad_concurrency)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_sha", ["z" * 64, "A" * 64, "0" * 63, 123])
async def test_noncanonical_receipt_digest_forces_reaudit(tmp_path, monkeypatch, bad_sha):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["sha256"] = bad_sha
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.valid is True and len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_first_ms", [253402300800000, 253402300800001])
async def test_out_of_range_first_timestamp_receipt_forces_reaudit(tmp_path, monkeypatch, bad_first_ms):
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["first_ms"] = bad_first_ms
    receipt["last_ms"] = bad_first_ms
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path)
    assert result.valid is True and len(calls) == 2


@pytest.mark.asyncio
async def test_cached_receipt_rejects_endpoints_outside_requested_day(tmp_path, monkeypatch):
    from datetime import date
    from market_data import archive_ingestion
    path = tmp_path / "archive.csv.gz"
    day = date(2025, 1, 1)
    calls = []

    async def fake_download(session, url, dest, **kwargs):
        calls.append(url)
        make_gzip(dest)
        return dest

    monkeypatch.setattr(archive_ingestion, "download_archive", fake_download)
    await acquire_archive(object(), URL, path, day=day)
    receipt_path = tmp_path / "archive.csv.gz.audit.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["first_ms"] = 1735603200000
    receipt["last_ms"] = 1735603200000
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = await acquire_archive(object(), URL, path, day=day)
    assert result.valid is True
    assert len(calls) == 2
