# Source Meta82 test_archive_etag_validation.py; canonical import transfer.
"""Strict ETag validation protects Range and If-Range request headers."""
import pytest

from market_data.archive_resume import ResumeState, resume_headers, strong_etag


@pytest.mark.parametrize("etag", [
    'W/"weak"', '"contains space"', '"embedded"quote"',
    '"tab\tinside"', '"newline\ninside"',
    '"carriage\rinside"', '""', "unquoted",
])
def test_reject_unsafe_or_weak_etag(etag):
    assert not strong_etag(etag)
    with pytest.raises(ValueError, match="strong ETag"):
        resume_headers(ResumeState(3, etag, 10))


def test_accept_strong_etag():
    assert strong_etag('"abc-123"')
    # RFC 9110 permits a backslash within an opaque ETag value.
    assert strong_etag('"backslash\\\\inside"')
    assert resume_headers(ResumeState(3, '"abc-123"', 10))["If-Range"] == '"abc-123"'


@pytest.mark.parametrize("etag", [
    '"x!"', '"x#"', '"x~"', '"x\\\\y"',
])
def test_strong_etag_accepts_rfc_visible_boundaries(etag):
    assert strong_etag(etag)


@pytest.mark.parametrize("etag", ['"x "', '"x\t"', '"x\n"', '"x\x7f"'])
def test_strong_etag_rejects_control_and_space(etag):
    assert not strong_etag(etag)
