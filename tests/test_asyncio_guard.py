import asyncio
import grid.asyncio_guard as guard


class FakeReset(ConnectionResetError):
    def __init__(self, winerror):
        super().__init__("reset")
        self.winerror = winerror


def test_expected_windows_proactor_reset_is_narrow(monkeypatch):
    monkeypatch.setattr(guard.os, "name", "nt")
    assert guard.is_expected_windows_proactor_reset({
        "exception": FakeReset(10054),
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
    })
    assert not guard.is_expected_windows_proactor_reset({
        "exception": FakeReset(10053),
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
    })
    assert not guard.is_expected_windows_proactor_reset({
        "exception": FakeReset(10054),
        "message": "different callback",
    })
    assert not guard.is_expected_windows_proactor_reset({
        "exception": RuntimeError("boom"),
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
    })


def test_guard_delegates_unexpected_exceptions(monkeypatch):
    monkeypatch.setattr(guard.os, "name", "nt")
    loop = asyncio.new_event_loop()
    seen = []

    def previous(active_loop, context):
        seen.append(context)

    loop.set_exception_handler(previous)
    try:
        guard.install_asyncio_exception_filter(loop)
        handler = loop.get_exception_handler()
        unexpected = {"exception": RuntimeError("boom"), "message": "unexpected"}
        handler(loop, unexpected)
        assert seen == [unexpected]

        handler(loop, {
            "exception": FakeReset(10054),
            "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
        })
        assert seen == [unexpected]
    finally:
        loop.close()


def test_coordinator_installs_asyncio_guard():
    source = open("grid/coordinator.py", encoding="utf-8").read()
    assert "from .asyncio_guard import install_asyncio_exception_filter" in source
    assert "install_asyncio_exception_filter(asyncio.get_running_loop())" in source
