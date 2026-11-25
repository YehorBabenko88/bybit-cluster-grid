# Original Meta82 test_archive_decompression_budget.py; canonical import transfer.
"""Decompression-budget regression tests for archive audits."""
import gzip

from market_data.bybit_archive_audit import audit_trade_gzip


def _archive(tmp_path, payload):
    path = tmp_path / "trades.csv.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(payload)
    return path


def test_decompression_budget_rejects_large_csv_header(tmp_path):
    path = _archive(tmp_path, b"timestamp,price,size," + b"x" * 10000 + b"\n")
    result = audit_trade_gzip(path, max_uncompressed_bytes=128)
    assert not result.valid
    assert "budget" in result.reason


def test_decompression_budget_rejects_large_row(tmp_path):
    path = _archive(tmp_path, b"trdMatchID,timestamp,price,size,side\nid1,1,2,3,Buy" + b" " * 10000 + b"\n")
    result = audit_trade_gzip(path, max_uncompressed_bytes=128)
    assert not result.valid
    assert "budget" in result.reason


def test_exact_decompression_budget_allows_valid_csv(tmp_path):
    payload = b"trdMatchID,timestamp,price,size,side\nid1,1,2,3,Buy\n"
    path = _archive(tmp_path, payload)
    result = audit_trade_gzip(path, max_uncompressed_bytes=len(payload))
    assert result.valid
    assert result.rows == 1
