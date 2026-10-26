import pytest

from grid.snapshot_source_epoch import SourceEpochBlocked, validate_source_epoch


def source(name, **changes):
    receipt = dict(source_id=name, epoch_id="epoch-1", routing_generation=7,
                   snapshot_id="snapshot-" + name, source_sha256="a" * 64)
    receipt.update(changes)
    return receipt


def check(receipts):
    validate_source_epoch(receipts, required_sources=frozenset({"pg", "sqlite"}),
                          expected_epoch="epoch-1", expected_routing_generation=7)


def test_complete_source_set():
    check([source("pg"), source("sqlite")])


@pytest.mark.parametrize("receipts", [
    [source("pg")],
    [source("pg"), source("pg")],
    [source("pg"), source("unexpected")],
    [source("pg"), source("sqlite", epoch_id="epoch-2")],
    [source("pg"), source("sqlite", routing_generation=6)],
    [source("pg"), source("sqlite", source_sha256="bad")],
])
def test_stale_duplicate_missing_sources_blocked(receipts):
    with pytest.raises(SourceEpochBlocked):
        check(receipts)
