import pytest

from grid.snapshot_historical_provenance import (
    HistoricalProvenanceBlocked, validate_historical_bar,
)


def row(**changes):
    data = dict(exchange="bybit", market_type="linear", symbol="BTCUSDT",
                event_ns=10, ingest_ns=20, first_available_ns=30,
                revision=1, revision_recorded_ns=25,
                producer_id="grid-fixture", source_epoch="epoch-1",
                history_complete=True)
    data.update(changes)
    return data


def test_complete_fixture_still_not_authenticated():
    result = validate_historical_bar(row(), knowledge_cutoff_ns=40)
    assert result["status"] == "STRUCTURE_ONLY"
    assert result["history_verified"] is False


@pytest.mark.parametrize("changes", [
    {"first_available_ns": None}, {"revision": 0},
    {"history_complete": False}, {"first_available_ns": 41},
    {"revision_recorded_ns": 35}, {"revision_recorded_ns": 19}, {"market_type": ""},
    {"ingest_ns": 50},
])
def test_unproven_history_rejected(changes):
    with pytest.raises(HistoricalProvenanceBlocked):
        validate_historical_bar(row(**changes), knowledge_cutoff_ns=40)


def test_missing_provenance_rejected():
    data = row()
    del data["revision_recorded_ns"]
    with pytest.raises(HistoricalProvenanceBlocked):
        validate_historical_bar(data, knowledge_cutoff_ns=40)
