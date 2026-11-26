# Original Meta82 test_bybit_archive_audit.py; canonical import transfer.
import csv
import gzip

from market_data.bybit_archive_audit import audit_trade_gzip


def write_archive(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["trdMatchID", "timestamp", "price", "size", "side"])
        writer.writeheader()
        writer.writerows({"trdMatchID": f"id{index}", "side": "Buy", **row} for index, row in enumerate(rows, 1))


def test_valid_archive_is_not_assumed_complete(tmp_path):
    path = tmp_path / "BTCUSDT.csv.gz"
    write_archive(path, [
        {"timestamp": "1735689600.001", "price": "100", "size": "0.1"},
        {"timestamp": "1735689600.002", "price": "101", "size": "0.2"},
    ])
    result = audit_trade_gzip(path)
    assert result.valid
    assert not result.complete
    assert result.rows == 2
    assert result.last_ms - result.first_ms == 1


def test_invalid_and_out_of_order_rows(tmp_path):
    path = tmp_path / "bad.csv.gz"
    write_archive(path, [
        {"timestamp": "1735689602", "price": "100", "size": "1"},
        {"timestamp": "1735689601", "price": "100", "size": "1"},
    ])
    assert not audit_trade_gzip(path).valid
    write_archive(path, [{"timestamp": "1735689600", "price": "NaN", "size": "1"}])
    assert not audit_trade_gzip(path).valid


def test_corrupt_and_empty_archive(tmp_path):
    path = tmp_path / "corrupt.csv.gz"
    path.write_bytes(b"not gzip")
    assert not audit_trade_gzip(path).valid
    write_archive(path, [])
    assert not audit_trade_gzip(path).valid
