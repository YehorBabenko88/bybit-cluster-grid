# Source Meta82 test_archive_resume.py; canonical import transfer.
import pytest

from market_data.archive_resume import ResumeState, resume_headers, validate_partial_response

STATE = ResumeState(offset=100, etag='"archive-v1"', total_bytes=250)
GOOD = {"Content-Range": "bytes 100-249/250", "ETag": '"archive-v1"',
        "Content-Length": "150"}


def test_strong_validator_and_exact_range():
    assert resume_headers(STATE) == {
        "Range": "bytes=100-", "If-Range": '"archive-v1"',
        "Accept-Encoding": "identity",
    }
    assert validate_partial_response(206, GOOD, STATE) == 150


@pytest.mark.parametrize("status,headers", [
    (200, GOOD),
    (206, {"Content-Range": "bytes 99-249/250"}),
    (206, {"Content-Range": "bytes 100-249/251"}),
    (206, {"Content-Range": "bytes 100-248/250"}),
    (206, {"Content-Range": "bytes 100-249/250", "ETag": '"archive-v2"'}),
    (206, {"Content-Range": "bytes 100-249/250", "Content-Length": "149"}),
    (206, {"Content-Range": "bytes 100-249/250", "Content-Encoding": "gzip"}),
])
def test_reject_unsafe_resume_response(status, headers):
    with pytest.raises(ValueError):
        validate_partial_response(status, headers, STATE)


@pytest.mark.parametrize("etag", ["W/\"weak\"", "", "unquoted", '"broken\r\n"'])
def test_resume_requires_strong_etag(etag):
    with pytest.raises(ValueError):
        resume_headers(ResumeState(100, etag, 250))
