"""Fail-closed Bybit orderbook state transitions."""
from decimal import Decimal
import pytest
from market_data.orderbook import OrderBook


def message(kind, uid, seq, bids=None, asks=None):
    return {"type": kind, "data": {"s": "BTCUSDT", "u": uid, "seq": seq,
            "b": [["100", "1"]] if bids is None else bids,
            "a": [["101", "1"]] if asks is None else asks}}


def test_delta_cannot_bootstrap_book_even_with_restart_uid():
    book = OrderBook("BTCUSDT")
    assert not book.apply(message("delta", 1, 1))
    assert not book.valid
    assert book.apply(message("snapshot", 1, 2))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_levels_fail_closed(bad):
    book = OrderBook("BTCUSDT")
    assert not book.apply(message("snapshot", 1, 1, bids=[["100", bad]]))
    assert not book.valid


@pytest.mark.parametrize("uid,seq", [(True, 1), ("2", 2), (-1, 2), (2, None)])
def test_invalid_update_ids_rejected(uid, seq):
    book = OrderBook("BTCUSDT")
    assert not book.apply(message("snapshot", uid, seq))
    assert not book.valid


def test_duplicate_and_out_of_order_require_new_snapshot():
    book = OrderBook("BTCUSDT")
    assert book.apply(message("snapshot", 1, 1))
    assert book.apply(message("delta", 2, 2))
    assert not book.apply(message("delta", 2, 3))
    assert not book.apply(message("delta", 3, 4))
    assert book.apply(message("snapshot", 5, 5))
    assert book.valid


def test_malformed_delta_clears_previously_valid_levels():
    book = OrderBook("BTCUSDT")
    assert book.apply(message("snapshot", 1, 1))
    assert not book.apply(message("delta", 2, 2, bids=[["99", "1"], ["98", "NaN"]]))
    assert not book.valid
    assert book.bids == {} and book.asks == {}
    assert not book.apply(message("delta", 3, 3))
    assert book.apply(message("snapshot", 4, 4))


@pytest.mark.parametrize("payload", [None, [], {"type": "delta"}, {"type": "delta", "data": []}])
def test_malformed_envelopes_invalidate(payload):
    book = OrderBook("BTCUSDT")
    assert book.apply(message("snapshot", 1, 1))
    assert not book.apply(payload)
    assert not book.valid
    assert book.bids == {} and book.asks == {}


def test_duplicate_prices_and_excessive_level_count_are_refused():
    for bids in ([["100", "1"], ["100", "2"]],
                 [[str(price), "1"] for price in range(1, 502)]):
        book = OrderBook('BTCUSDT')
        assert not book.apply(message('snapshot', 1, 1, bids=bids, asks=[["1000", "1"]]))
        assert not book.valid and not book.bids and not book.asks


def test_market_numeric_domain_and_update_id_bounds_are_closed():
    for payload in (
        message('snapshot', 2**63, 1),
        message('snapshot', 1, 2**63),
        message('snapshot', 1, 1, bids=[["1e1001", "1"]], asks=[["2e1001", "1"]]),
        message('snapshot', 1, 1, bids=[["100", "1e-1001"]]),
    ):
        book = OrderBook('BTCUSDT')
        assert not book.apply(payload)
        assert not book.valid


def test_state_validation_does_not_use_callers_decimal_context():
    from decimal import Context, localcontext
    context = Context(prec=1, Emin=-2, Emax=2)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context) as caller:
        book = OrderBook('BTCUSDT')
        assert book.apply(message('snapshot', 1, 1, bids=[["100", "1e-1000"]]))
        assert book.bids[Decimal('100')] == Decimal('1e-1000')
        assert not any(caller.flags.values())
