import copy
import hashlib

import pytest

from grid.historical_science_import import canonical_payload, verify_bundle


def signed(**changes):
    value = {"schema": 1, "source": "strattester", "created_at": 1.0,
             "research_scope": "HISTORICAL_BOOTSTRAP_ONLY",
             "capabilities": {"candles": True, "open_interest": True,
                              "public_trade_aggregates": True},
             "symbols": [{"symbol": "BTCUSDT", "samples": 2,
                          "from_ms": 100, "through_ms": 200,
                          "summary": {}, "features": {}}]}
    value.update(changes)
    value["sha256"] = hashlib.sha256(canonical_payload(value).encode()).hexdigest()
    return value


@pytest.mark.parametrize("schema", [2, True, "1", None])
def test_unknown_or_malformed_schema_is_rejected_even_with_valid_hash(schema):
    assert verify_bundle(signed(schema=schema))[0] is False


@pytest.mark.parametrize("created", [float("nan"), float("inf"), -1, True, "1", 10**400])
def test_invalid_source_timestamp_is_rejected(created):
    assert verify_bundle(signed(created_at=created))[0] is False


@pytest.mark.parametrize("capability", ["false", 1, [], None])
def test_capabilities_require_json_booleans(capability):
    value = signed()
    caps = dict(value["capabilities"], candles=capability)
    assert verify_bundle(signed(capabilities=caps))[0] is False


@pytest.mark.parametrize("field,value", [
    ("samples", -1), ("samples", True), ("samples", 2**63),
    ("from_ms", -1), ("from_ms", 100.5), ("from_ms", True),
    ("through_ms", 2**63), ("through_ms", 50),
    ("symbol", ""), ("symbol", None),
    ("summary", {"mean": float("nan")}),
    ("features", {"price": float("inf")}),
])
def test_invalid_symbol_state_is_rejected(field, value):
    item = copy.deepcopy(signed()["symbols"][0])
    item[field] = value
    assert verify_bundle(signed(symbols=[item]))[0] is False


@pytest.mark.parametrize("symbols", [{}, [None], ["BTCUSDT"]])
def test_malformed_symbol_container_is_rejected(symbols):
    assert verify_bundle(signed(symbols=symbols))[0] is False


def test_duplicate_symbol_states_are_rejected():
    item = signed()["symbols"][0]
    assert verify_bundle(signed(symbols=[item, item]))[0] is False


def test_minimal_insufficient_symbol_state_remains_supported():
    assert verify_bundle(signed(symbols=[{"symbol": "NEWUSDT", "samples": 0,
                                         "status": "INSUFFICIENT"}])) == (True, None)
