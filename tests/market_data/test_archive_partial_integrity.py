# Source Meta82 test_archive_partial_integrity.py; canonical import transfer.
import pytest

from market_data.archive_partial_state import partial_paths, read_partial, save_partial
from market_data.archive_resume import ResumeState

URL = "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz"


def test_same_size_corruption_invalidates_resume(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, _ = partial_paths(dest)
    partial.write_bytes(b"abc")
    state = ResumeState(3, '"v1"', 10)
    save_partial(dest, URL, state)
    assert read_partial(dest, URL) == state
    partial.write_bytes(b"abd")
    assert read_partial(dest, URL) is None


def test_missing_hash_in_legacy_sidecar_rejected(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, sidecar = partial_paths(dest)
    partial.write_bytes(b"abc")
    sidecar.write_text('{"url": "' + URL +
                       '", "etag": "\\"v1\\"", "total_bytes": 10, "offset": 3}')
    assert read_partial(dest, URL) is None


def test_checkpoint_url_mismatch_rejected(tmp_path):
    dest = tmp_path / "archive.csv.gz"
    partial, _ = partial_paths(dest)
    partial.write_bytes(b"abc")
    save_partial(dest, URL, ResumeState(3, '"v1"', 10))
    assert read_partial(dest, URL.replace("BTCUSDT", "ETHUSDT")) is None
