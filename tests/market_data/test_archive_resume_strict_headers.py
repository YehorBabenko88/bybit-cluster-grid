# Source Meta82 test_archive_resume_strict_headers.py; canonical import transfer.
"""Regression tests for resumed HTTP response identity and size."""

import pytest

from market_data.archive_resume import ResumeState, validate_partial_response


STATE = ResumeState(3, '"v1"', 10)
BASE = {"Content-Range": "bytes 3-9/10", "ETag": '"v1"', "Content-Length": "7"}


def test_matching_resume_headers_accepted():
    assert validate_partial_response(206, BASE, STATE) == 7


@pytest.mark.parametrize("missing", ["ETag", "Content-Length", "Content-Range"])
def test_required_resume_header_missing(missing):
    headers = {key: value for key, value in BASE.items() if key != missing}
    with pytest.raises(ValueError):
        validate_partial_response(206, headers, STATE)


@pytest.mark.parametrize("replacement", ['"v2"', 'W/"v1"'])
def test_etag_mismatch_rejected(replacement):
    with pytest.raises(ValueError):
        validate_partial_response(206, {**BASE, "ETag": replacement}, STATE)


@pytest.mark.parametrize("length", ["garbage", "-1", "8"])
def test_invalid_or_wrong_length_rejected(length):
    with pytest.raises(ValueError):
        validate_partial_response(206, {**BASE, "Content-Length": length}, STATE)


def test_server_ignoring_range_rejected():
    with pytest.raises(ValueError):
        validate_partial_response(200, BASE, STATE)
