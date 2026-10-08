import math
import pytest

from grid.orderbook import parse_book_levels


def test_parse_book_levels_accepts_valid_snapshot_and_zero_removal_delta():
    assert parse_book_levels([["100.5","2"],["99","3"]],snapshot=True)=={100.5:2.0,99.0:3.0}
    assert parse_book_levels([["100.5","0"]])=={100.5:0.0}


@pytest.mark.parametrize("levels",[
    None,{},[["100"]],[["100","1","extra"]],
    [["nan","1"]],[["inf","1"]],[["-1","1"]],
    [["100","nan"]],[["100","inf"]],[["100","-1"]],
    [["abc","2"]],[[None,"1"]],
])
def test_parse_book_levels_rejects_invalid_values(levels):
    with pytest.raises(ValueError):
        parse_book_levels(levels)


def test_snapshot_rejects_zero_quantity():
    with pytest.raises(ValueError):
        parse_book_levels([["100","0"]],snapshot=True)
