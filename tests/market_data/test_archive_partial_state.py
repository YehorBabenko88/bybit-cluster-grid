# Source Meta82 test_archive_partial_state.py; canonical import transfer.
import json

import pytest

from market_data.archive_partial_state import (
    discard_partial, partial_paths, read_partial, save_partial,
)
from market_data.archive_resume import ResumeState


URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


def test_partial_state_roundtrip_and_cleanup(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, sidecar = partial_paths(dest)
    partial.write_bytes(b"abc")
    state = ResumeState(3, '"v1"', 10)
    save_partial(dest, URL, state)
    assert read_partial(dest, URL) == state
    assert read_partial(dest, URL + "other") is None
    assert read_partial(dest, URL, max_bytes=9) is None
    discard_partial(dest)
    assert not partial.exists() and not sidecar.exists()


def test_changed_partial_file_rejected(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, _ = partial_paths(dest)
    partial.write_bytes(b"abc")
    save_partial(dest, URL, ResumeState(3, '"v1"', 10))
    partial.write_bytes(b"ab")
    assert read_partial(dest, URL) is None


def test_corrupt_or_weak_validator_rejected(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, sidecar = partial_paths(dest)
    partial.write_bytes(b"abc")
    sidecar.write_text(json.dumps({
        "url": URL, "etag": 'W/"weak"', "total_bytes": 10, "offset": 3
    }))
    assert read_partial(dest, URL) is None
    sidecar.write_text("{bad json")
    assert read_partial(dest, URL) is None


def test_state_cannot_claim_bytes_not_written(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, _ = partial_paths(dest)
    partial.write_bytes(b"abc")
    with pytest.raises(ValueError, match="size"):
        save_partial(dest, URL, ResumeState(4, '"v1"', 10))
