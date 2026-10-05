import logging
import os


def is_expected_windows_proactor_reset(context):
    """Recognize only the benign Windows Proactor peer-reset callback."""
    exc = context.get("exception")
    handle = context.get("handle")
    message = str(context.get("message", ""))
    callback = getattr(handle, "_callback", None)
    callback_name = getattr(callback, "__qualname__", "")
    return (
        os.name == "nt"
        and isinstance(exc, ConnectionResetError)
        and getattr(exc, "winerror", None) == 10054
        and (
            "_ProactorBasePipeTransport._call_connection_lost" in message
            or "_ProactorBasePipeTransport._call_connection_lost" in callback_name
        )
    )


def install_asyncio_exception_filter(loop):
    """Drop routine peer resets; preserve normal asyncio exception reporting."""
    previous = loop.get_exception_handler()

    def handler(active_loop, context):
        if is_expected_windows_proactor_reset(context):
            logging.getLogger("asyncio").debug(
                "remote peer reset Windows Proactor transport",
                extra={
                    "event": "windows_proactor_peer_reset",
                    "component": "asyncio",
                },
            )
            return
        if previous is not None:
            previous(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
    return handler
