"""Conservative HTTP Range validation for resumable public archives.

Never append bytes to a partial download unless the server proves the
requested offset and a strong entity validator matches the saved response.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


_CONTENT_RANGE = re.compile(r"bytes (0|[1-9][0-9]*)-(0|[1-9][0-9]*)/(0|[1-9][0-9]*)\Z")


@dataclass(frozen=True)
class ResumeState:
    offset: int
    etag: str
    total_bytes: int


def strong_etag(value: str | None) -> bool:
    return bool(value and re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]+"', value))


def resume_headers(state: ResumeState) -> dict[str, str]:
    if (type(state.offset) is not int or type(state.total_bytes) is not int
            or not 1 <= state.offset < state.total_bytes <= 2_000_000_000):
        raise ValueError("invalid resume offset")
    if not strong_etag(state.etag):
        raise ValueError("resume requires a strong ETag")
    return {"Range": f"bytes={state.offset}-", "If-Range": state.etag,
            "Accept-Encoding": "identity"}


def validate_partial_response(status: int, headers, state: ResumeState) -> int:
    """Return expected remaining bytes; reject fallback 200 and mismatched ranges."""
    resume_headers(state)
    if status != 206:
        raise ValueError("server did not honor partial content request")
    match = _CONTENT_RANGE.fullmatch(headers.get("Content-Range", ""))
    if match is None:
        raise ValueError("missing or invalid Content-Range")
    start, end, total = map(int, match.groups())
    if start != state.offset or total != state.total_bytes or end != total - 1:
        raise ValueError("range does not match saved archive")
    etag = headers.get("ETag")
    if etag != state.etag:
        raise ValueError("archive ETag missing or changed")
    if headers.get("Content-Encoding", "identity").lower() != "identity":
        raise ValueError("compressed HTTP transfer encoding not supported for resume")
    length = headers.get("Content-Length")
    expected = total - start
    if length is None:
        raise ValueError("range response missing Content-Length")
    try:
        declared = int(length)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid Content-Length") from exc
    if declared != expected:
        raise ValueError("range response length mismatch")
    return expected
