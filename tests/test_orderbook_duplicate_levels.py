import pytest

from grid.orderbook import parse_book_levels


@pytest.mark.parametrize("snapshot", [True, False])
def test_duplicate_price_levels_are_rejected(snapshot):
    with pytest.raises(ValueError, match="duplicate"):
        parse_book_levels([["100","1"],["100.0","2"]],snapshot=snapshot)


def test_distinct_price_levels_remain_valid():
    assert parse_book_levels([["100","1"],["101","2"]])=={100.0:1.0,101.0:2.0}


def test_single_delta_zero_quantity_is_valid():
    assert parse_book_levels([["100","0"]])=={100.0:0.0}
