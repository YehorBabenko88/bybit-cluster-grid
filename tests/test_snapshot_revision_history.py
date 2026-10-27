import pytest
from grid.snapshot_revision_history import validate_revision_history
from grid.snapshot_historical_provenance import HistoricalProvenanceBlocked


def revision(number, **changes):
    row = dict(exchange="bybit", market_type="linear", symbol="BTCUSDT",
               event_ns=10, ingest_ns=20, first_available_ns=30 + number,
               revision=number, revision_recorded_ns=20 + number,
               producer_id="grid-fixture", source_epoch="epoch-1",
               history_complete=True)
    row.update(changes)
    return row


def test_ordered_history_is_structure_only():
    result = validate_revision_history([revision(1), revision(2)],
                                       knowledge_cutoff_ns=100)
    assert result["history_verified"] is False


@pytest.mark.parametrize("rows", [
    [revision(2)],
    [revision(1), revision(1)],
    [revision(1), revision(3)],
    [revision(1), revision(2, revision_recorded_ns=20)],
    [revision(1), revision(2, first_available_ns=30)],
])
def test_invalid_revision_history_rejected(rows):
    with pytest.raises(HistoricalProvenanceBlocked):
        validate_revision_history(rows, knowledge_cutoff_ns=100)
