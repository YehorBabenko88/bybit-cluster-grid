import asyncio

import grid.control_replication as replication
from grid.control_version_vector import compare_vectors, freshest_dominating


def r(a, b):
    return {
        "state": {
            "telegram_cursor": {"_version": a},
            "leader_epoch": {"_version": b},
        }
    }


def test_version_vector_selects_only_dominating_replica():
    assert compare_vectors({"a": 2, "b": 3}, {"a": 1, "b": 3}) == 1
    assert freshest_dominating([r(1, 1), r(2, 1), r(2, 3)]) == r(2, 3)


def test_concurrent_control_states_are_not_guessed():
    try:
        freshest_dominating([r(3, 1), r(2, 2)])
        assert False
    except ValueError:
        pass


def test_json_object_accepts_dict():
    value = {"next_update_id": 123}
    assert replication._json_object(value) == value


def test_json_object_decodes_jsonb_string():
    value = '{"next_update_id":100376615}'
    assert replication._json_object(value) == {"next_update_id": 100376615}


def test_json_object_fails_closed_for_invalid_values():
    assert replication._json_object(None) == {}
    assert replication._json_object("") == {}
    assert replication._json_object("not-json") == {}
    assert replication._json_object("[]") == {}
    assert replication._json_object(["wrong-type"]) == {}


def test_telegram_cursor_reads_jsonb_string(monkeypatch):
    async def fake_get_control_state(pool, key):
        assert key == "telegram_cursor"
        return {
            "value": '{"next_update_id":100376615}',
            "version": 1,
        }

    monkeypatch.setattr(
        replication,
        "get_control_state",
        fake_get_control_state,
    )

    result = asyncio.run(
        replication.telegram_cursor(object())
    )

    assert result == 100376615


def test_commit_telegram_cursor_advances_from_jsonb_string():
    class Pool:
        async def fetchrow(self, sql, *args):
            assert "ON CONFLICT" in sql
            assert args == (100376616, "CONTROL")
            return {"next_update_id": 100376616}

    result = asyncio.run(
        replication.commit_telegram_cursor(Pool(), "CONTROL", 100376616)
    )
    assert result == 100376616


def test_commit_telegram_cursor_never_moves_backwards(monkeypatch):
    class Pool:
        async def fetchrow(self, sql, *args):
            assert "ON CONFLICT" in sql
            return None

    async def fake_get_control_state(pool, key):
        assert key == "telegram_cursor"
        return {"value": '{"next_update_id":100376616}', "version": 2}

    monkeypatch.setattr(replication, "get_control_state", fake_get_control_state)
    result = asyncio.run(
        replication.commit_telegram_cursor(Pool(), "CONTROL", 100376615)
    )
    assert result == 100376616
