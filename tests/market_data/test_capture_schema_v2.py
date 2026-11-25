"""Exclusive active v2 with read-only unchanged historical v1 decoding."""
import hashlib,json
from pathlib import Path
import pytest
from market_data.historical_capture import decode_v1_observation
from market_data.raw_capture import encode_observation,decode_observation,RawCaptureError
import test_capture_recorder as recorder_fixtures

def test_historical_fixture_stays_raw_and_active_encoder_refuses_v1():
    raw=(Path(__file__).parent/'fixtures/raw-v1-observation.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='63c9d7e616a26b7d511d0a36e31d1d4d0c6f8862b4df120433dadf810a9a99e5'
    value=decode_v1_observation(raw)
    assert value['schema']=='market_data.raw-capture-observation.v1-review1'
    with pytest.raises(RawCaptureError):encode_observation(value)
    with pytest.raises(RawCaptureError):decode_observation(raw)

def test_all_current_ws_recorder_output_is_v2_with_no_archive_alias():
    case=recorder_fixtures.RecorderTests();case.setUp();case.frame(b'current');raw=case.sink.records[0][0]
    current=decode_observation(raw)
    assert current['schema']=='market_data.raw-capture-observation.v2' and current['archive'] is None
    with pytest.raises(ValueError):decode_v1_observation(raw)
