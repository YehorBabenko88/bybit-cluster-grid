# Original Meta82 test_archive_csv_profile.py; canonical import transfer.
"""Shared CSV acceptance profile for archive audit and storage importer."""
import gzip

import pytest

from market_data.bybit_archive_audit import audit_trade_gzip


HEADER = "trdMatchID,timestamp,price,size,side\n"
GOOD = "id1,1735689600.123456,100.5,1.25,Buy\n"


@pytest.mark.parametrize(
    ("csv_text", "valid"),
    [
        (HEADER + GOOD, True),
        ("\ufeff" + HEADER + GOOD, True),
        ("timestamp,price,size\n1735689600,100,1\n", False),
        ("trdMatchID,timestamp,price,size,side,side\n" + "id1,1735689600,100,1,Buy,Buy\n", False),
        (HEADER + "id1,1735689600,100,1,Buy,extra\n", False),
        (HEADER + "id1,1735689600,100,1\n", False),
        (HEADER + "id1,1735689600,100,1,Buy\n\n", True),
        (HEADER + ",1735689600,100,1,Buy\n", False),
        (HEADER + "id1,1735689600,100,1,Unknown\n", False),
        (HEADER + "id1,1735689600,100,0,Buy\n", False),
        (HEADER + "id1,1735689600,0,1,Buy\n", False),
        (HEADER + "id1,NaN,100,1,Buy\n", False),
        (HEADER + "id1,1735689600,Infinity,1,Buy\n", False),
        (HEADER + "id1,1735689600,100,-1,Buy\n", False),
        (HEADER + "id1,1735689600,100,1,Buy\nid2,1735689600,100,1,Sell\n", True),
        (HEADER + "id1,253402300800,100,1,Buy\n", False),
        (HEADER + "id1,1735689601,100,1,Buy\nid2,1735689600,100,1,Sell\n", False),
        (HEADER + "id1,1735689600.000900,100,1,Buy\nid2,1735689600.000100,100,1,Sell\n", False),
        (HEADER + "id1,1735689600.000100,100,1,Buy\nid2,1735689600.000900,100,1,Sell\n", True),
        (HEADER, False),
    ],
)
def test_archive_csv_strict_profile(tmp_path, csv_text, valid):
    path = tmp_path / "trades.csv.gz"
    path.write_bytes(gzip.compress(csv_text.encode("utf-8")))
    result = audit_trade_gzip(path)
    assert result.valid is valid, result.reason
    assert result.complete is False


@pytest.mark.parametrize(("raw_timestamp", "expected_ms"), [
    ("1735775999.999999999999999999999", 1735775999999),
    ("253402300799.99999999999999999", 253402300799999),
    ("1735689600.000000999999999999999", 1735689600000),
])
def test_timestamp_milliseconds_never_round_across_boundary(tmp_path, raw_timestamp, expected_ms):
    path = tmp_path / "precise.csv.gz"
    path.write_bytes(gzip.compress((HEADER + f"id1,{raw_timestamp},100,1,Buy\n").encode("utf-8")))
    audit = audit_trade_gzip(path)
    assert audit.valid, audit.reason
    assert audit.first_ms == expected_ms
    assert audit.last_ms == expected_ms


@pytest.mark.parametrize("bad_budget", [0, -1, True, False, 1.5, "10"])
@pytest.mark.parametrize("field", ["max_rows", "max_uncompressed_bytes"])
def test_audit_rejects_invalid_resource_budget_before_opening_file(tmp_path, field, bad_budget):
    path = tmp_path / "missing.csv.gz"
    with pytest.raises(ValueError, match="audit budgets must be positive integers"):
        audit_trade_gzip(path, **{field: bad_budget})


def test_archive_rejects_unterminated_quoted_csv_field(tmp_path):
    path = tmp_path / "malformed.csv.gz"
    path.write_bytes(gzip.compress((HEADER + 'id1,1735689600,100,1,"Buy\n').encode("utf-8")))
    audit = audit_trade_gzip(path)
    assert audit.valid is False
    assert audit.complete is False


@pytest.mark.parametrize("raw_timestamp", ["1e-999999999", "0e-999999999", "1e-7"])
def test_archive_extreme_tiny_timestamp_does_not_allocate_huge_power(tmp_path, raw_timestamp):
    path = tmp_path / "tiny.csv.gz"
    path.write_bytes(gzip.compress((HEADER + f"id1,{raw_timestamp},100,1,Buy\n").encode("utf-8")))
    audit = audit_trade_gzip(path)
    assert audit.valid, audit.reason
    assert audit.first_ms == 0
    assert audit.last_ms == 0
    assert audit.complete is False
