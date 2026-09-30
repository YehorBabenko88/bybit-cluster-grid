import json

from grid.fleet_control import _json_value


def test_json_value_decodes_jsonb_object_text():
    raw = json.dumps({
        "PC4-c497e08e5efa": {
            "bootstrap_paused": False,
            "operator_stopped": False,
        }
    })

    value = _json_value(raw, {})

    assert value == {
        "PC4-c497e08e5efa": {
            "bootstrap_paused": False,
            "operator_stopped": False,
        }
    }


def test_json_value_decodes_jsonb_array_text():
    raw = '["PC4-c497e08e5efa"]'

    value = _json_value(raw, [])

    assert value == ["PC4-c497e08e5efa"]
    assert list(value) == ["PC4-c497e08e5efa"]


def test_json_value_preserves_already_decoded_values():
    snapshot = {
        "PC4-c497e08e5efa": {
            "operator_stopped": False,
        }
    }
    targets = ["PC4-c497e08e5efa"]

    assert _json_value(snapshot, {}) is snapshot
    assert _json_value(targets, []) is targets


def test_json_value_fails_closed_on_invalid_json():
    assert _json_value("not-json", {}) == {}
    assert _json_value("not-json", []) == []
