import pytest
from grid.snapshot_source_cut import SourceCutBlocked, validate_source_cuts


def cut(name, **changes):
    item = dict(source_id=name, epoch_id="epoch-1",
                snapshot_id="snapshot-" + name, cut_time_ns=90,
                knowledge_cutoff_ns=100, producer_attested=True)
    item.update(changes)
    return item


def check(cuts):
    return validate_source_cuts(
        cuts, expected_epoch="epoch-1",
        expected_sources=frozenset({"pg", "sqlite"}),
        knowledge_cutoff_ns=100)


def test_complete_cut_is_structure_only():
    result = check([cut("pg"), cut("sqlite")])
    assert result["status"] == "STRUCTURE_ONLY"
    assert result["coherence_verified"] is False


@pytest.mark.parametrize("bad", [
    [cut("pg")],
    [cut("pg"), cut("pg")],
    [cut("pg"), cut("sqlite", epoch_id="other")],
    [cut("pg"), cut("sqlite", cut_time_ns=101)],
    [cut("pg"), cut("sqlite", producer_attested=False)],
    [cut("pg"), cut("sqlite", knowledge_cutoff_ns=99)],
])
def test_invalid_source_cuts_rejected(bad):
    with pytest.raises(SourceCutBlocked):
        check(bad)
