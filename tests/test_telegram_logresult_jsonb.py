import json

from grid.telegram_bot import _decode_command_result


def test_decode_command_result_accepts_mapping():
    result = {"lines": ["one", "two"]}
    assert _decode_command_result(result) is result


def test_decode_command_result_decodes_json_string():
    assert _decode_command_result(json.dumps({"lines": ["one"]})) == {"lines": ["one"]}


def test_decode_command_result_preserves_plain_string_as_message():
    assert _decode_command_result("plain text") == {"message": "plain text"}


def test_decode_command_result_normalizes_non_mapping_json():
    assert _decode_command_result("[1, 2]") == {"message": "[1, 2]"}
