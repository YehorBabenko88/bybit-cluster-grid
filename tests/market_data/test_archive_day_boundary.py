# Original Meta82 test_archive_day_boundary.py; canonical import transfer.
from datetime import date

import pytest

from market_data.archive_day_boundary import utc_day_boundary, validate_day_audit
from market_data.bybit_archive_audit import ArchiveAudit


def test_utc_day_boundary_is_half_open():
    boundary = utc_day_boundary(date(2025, 1, 1))
    assert boundary.start_ms == 1735689600000
    assert boundary.end_ms == 1735776000000


def test_valid_endpoints_are_inside_day():
    boundary = utc_day_boundary(date(2025, 1, 1))
    audit = ArchiveAudit(2, boundary.start_ms, boundary.end_ms - 1,
                         True, False, "parsed")
    validate_day_audit(audit, boundary.day)


@pytest.mark.parametrize("offset", [-1, 86400000])
def test_out_of_day_endpoints_rejected(offset):
    boundary = utc_day_boundary(date(2025, 1, 1))
    audit = ArchiveAudit(1, boundary.start_ms + offset,
                         boundary.start_ms + offset, True, False, "parsed")
    with pytest.raises(ValueError, match="outside"):
        validate_day_audit(audit, boundary.day)


def test_invalid_audit_rejected():
    audit = ArchiveAudit(0, None, None, False, False, "invalid")
    with pytest.raises(ValueError, match="not passed"):
        validate_day_audit(audit, date(2025, 1, 1))
