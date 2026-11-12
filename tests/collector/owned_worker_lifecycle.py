"""Inert actual-service class tests: no Worker/dependency import or event loop.

Only the unchanged class AST is compiled; its imports/CLI are not executed.
Worker/web/asyncio collaborators are explicit in-memory doubles. Not E2E.
"""
import ast
import asyncio
from pathlib import Path
import types
import unittest

PROFILE = 'grid.data-only-collector.v1'


def finish(coro):
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    finally:
        coro.close()
    raise AssertionError('inert coroutine unexpectedly suspended')


class Task:
    def __init__(self, coro=None, error=None):
        self.coro, self.error = coro, error
        self.cancelled = False
        self.finished = error is not None
    def cancel(self):
        if getattr(self, 'ignore_cancel', False):
            return
        if not self.finished:
            self.cancelled = True
            self.finished = True
            if self.coro:
                self.coro.close()
    def done(self): return self.finished
    def result(self):
        if self.error: raise self.error
        if self.cancelled: raise asyncio.CancelledError()
        return None
    def __await__(self):
        if not self.finished and self.coro is not None:
            if getattr(self, 'running', False):
                yield ('WAIT_TASK', self)
                return self.result()
            self.running = True
            try:
                self.value = yield from self.coro.__await__()
            except BaseException as error:
                self.error = error
            finally:
                self.running = False
            self.finished = True
        if self.finished and not self.error and not self.cancelled:
            return getattr(self, 'value', None)
        return self.result()


class OwnedWorkerLifecycle(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.tasks = []
        self.site_error = None
        self.runner_error = None
        self.offline_calls = []
        self.offline_error = None
        self.offline_result = object()
        self.site_pause = False
        owner = self
        self.verify_pause = False
        class Pause:
            def __await__(self):
                yield 'PAUSE'
        self.Pause = Pause
        class Worker:
            def __init__(self, **kw): owner.calls.append(kw)
            async def run(self): raise AssertionError('fake worker must not execute')
            async def receive_offline(self, frames, **kw):
                owner.offline_calls.append((frames, kw))
                if owner.offline_error: raise owner.offline_error
                return owner.offline_result
        class Runner:
            async def setup(self): pass
            async def cleanup(self):
                if owner.runner_error: raise owner.runner_error
        class Site:
            def __init__(self, *args):
                self._server = types.SimpleNamespace(sockets=[types.SimpleNamespace(getsockname=lambda: ('127.0.0.1', 8766))])
            async def start(self):
                if owner.site_pause: await Pause()
                if owner.site_error: raise owner.site_error
        class Async:
            CancelledError = asyncio.CancelledError
            @staticmethod
            async def to_thread(fn):
                if owner.verify_pause: await Pause()
                return True  # source verifier collaborator, never called
            @staticmethod
            async def wait_for(coro, timeout): return await coro
            @staticmethod
            def create_task(coro, **kw):
                task = Task(coro)
                if kw.get('name') == 'owned-grid-listener-start' and owner.site_pause:
                    task.ignore_cancel = True
                owner.tasks.append(task)
                return task
            @staticmethod
            async def sleep(delay): pass
            @staticmethod
            async def shield(task): return await task
            @staticmethod
            async def gather(*tasks, return_exceptions=False):
                results = []
                for task in tasks:
                    try: results.append(await task)
                    except BaseException as error:
                        if not return_exceptions: raise
                        results.append(error)
                return results
        identity = ('grid', 'v', 'release', 'token', 'head')
        web = types.SimpleNamespace(Application=lambda **kw: types.SimpleNamespace(router=types.SimpleNamespace(add_route=lambda *a: None)),
                                    AppRunner=lambda *a, **kw: Runner(), TCPSite=Site)
        source = Path(__file__).absolute().parents[2] / 'grid/owned_worker_service.py'
        tree = ast.parse(source.read_bytes(), filename=str(source))
        cls, = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'OwnedWorkerService']
        namespace = dict(asyncio=Async, Worker=Worker, web=web,
                         binding=types.SimpleNamespace(_owned_module_identity=lambda: identity),
                         settings=types.SimpleNamespace(role='worker'))
        serve, = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'serve']
        exec(compile(ast.Module(body=[cls, serve], type_ignores=[]), str(source), 'exec'), namespace)
        self.Service = namespace['OwnedWorkerService']
        self.namespace = namespace

    def tearDown(self):
        for task in self.tasks:
            if task.coro: task.coro.close()

    def test_profile_rejects_unknown_before_worker(self):
        with self.assertRaises(ValueError): self.Service(launch_profile='FULL')
        self.assertEqual(self.calls, [])

    def test_data_only_requires_factory(self):
        with self.assertRaises(ValueError): self.Service(launch_profile=PROFILE)

    def test_data_only_rejects_research_admission(self):
        with self.assertRaises(ValueError):
            self.Service(launch_profile=PROFILE, raw_capture_factory=lambda: None, data_first_admission=object())

    def test_noncallable_factory_rejected(self):
        with self.assertRaises(ValueError): self.Service(raw_capture_factory=object())

    def test_legacy_default_worker_kwargs_unchanged(self):
        service = self.Service()
        finish(service.start(0))
        self.assertEqual(self.calls, [dict(data_first_admission=None)])
        finish(service.close())

    def test_same_raw_factory_forwarded_once(self):
        factory = lambda: None
        service = self.Service(raw_capture_factory=factory)
        finish(service.start(0))
        self.assertIs(self.calls[0]['raw_capture_factory'], factory)
        self.assertEqual(len(self.calls), 1)
        finish(service.close())

    def test_data_only_cannot_enter_listener_start(self):
        service = self.Service(launch_profile=PROFILE, raw_capture_factory=lambda: None)
        with self.assertRaises(RuntimeError): finish(service.start(0))
        self.assertEqual(self.calls, [])

    def test_worker_failure_not_swallowed_by_close(self):
        service = self.Service()
        error = RuntimeError('actual task failure')
        service.task = Task(error=error)
        with self.assertRaises(RuntimeError) as caught: finish(service.close())
        self.assertIs(caught.exception, error)

    def test_runner_cleanup_failure_still_retires_worker(self):
        service = self.Service()
        service.task = Task()
        self.runner_error = RuntimeError('cleanup failed')
        service.runner = types.SimpleNamespace(cleanup=self.cleanup_failure)
        with self.assertRaises(RuntimeError): finish(service.close())
        self.assertTrue(service.task.done())

    async def cleanup_failure(self): raise self.runner_error

    def test_start_failure_cancels_owned_task(self):
        service = self.Service()
        self.site_error = RuntimeError('site failed')
        with self.assertRaises(RuntimeError): finish(service.start(0))
        self.assertTrue(self.tasks[0].cancelled)

    def test_close_before_start_does_not_allow_later_start(self):
        service = self.Service()
        finish(service.close())
        with self.assertRaises(RuntimeError): finish(service.start(0))
        self.assertEqual(self.calls, [])

    def test_offline_exact_forwarding_without_listener_or_full_run(self):
        frames = (b'raw',)
        factory = lambda: None
        service = self.Service(launch_profile=PROFILE, raw_capture_factory=factory)
        result = finish(service.run_offline(frames, symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        self.assertIs(result, self.offline_result)
        self.assertIs(self.offline_calls[0][0], frames)
        self.assertEqual(self.offline_calls[0][1], dict(symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        self.assertIs(self.calls[0]['raw_capture_factory'], factory)
        self.assertEqual(self.calls[0]['launch_profile'], PROFILE)
        self.assertIsNone(service.runner)
        with self.assertRaises(RuntimeError):
            finish(service.run_offline(frames, symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        self.assertEqual(len(self.calls), 1)

    def test_offline_worker_error_is_retained_and_cannot_retry(self):
        service = self.Service(launch_profile=PROFILE, raw_capture_factory=lambda: None)
        self.offline_error = RuntimeError('receive failed')
        with self.assertRaises(RuntimeError) as caught:
            finish(service.run_offline((b'raw',), symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        self.assertIs(caught.exception, self.offline_error)
        with self.assertRaises(RuntimeError) as again: finish(service.close())
        self.assertIs(again.exception, self.offline_error)

    def test_offline_requires_explicit_profile_before_worker(self):
        service = self.Service(raw_capture_factory=lambda: None)
        with self.assertRaises(RuntimeError):
            finish(service.run_offline((b'raw',), symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        self.assertEqual(self.calls, [])

    def test_offline_cancellation_remains_observable(self):
        service = self.Service(launch_profile=PROFILE, raw_capture_factory=lambda: None)
        self.offline_error = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            finish(service.run_offline((b'raw',), symbol='BTCUSDT', endpoint='synthetic://bybit/linear', observed_at_ms=1))
        with self.assertRaises(asyncio.CancelledError): finish(service.close())
        self.assertTrue(service.task.done())

    def test_unrequested_task_cancellation_not_silenced(self):
        service = self.Service()
        service.task = Task(error=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError): finish(service.close())

    def test_both_shutdown_errors_are_retained(self):
        service = self.Service()
        self.runner_error = RuntimeError('runner failed')
        worker_error = RuntimeError('worker failed')
        service.runner = types.SimpleNamespace(cleanup=self.cleanup_failure)
        service.task = Task(error=worker_error)
        with self.assertRaises(BaseExceptionGroup) as caught: finish(service.close())
        self.assertEqual(caught.exception.exceptions, (self.runner_error, worker_error))

    def test_close_during_source_binding_prevents_late_worker_creation(self):
        service = self.Service()
        self.verify_pause = True
        startup = service.start(0)
        self.assertEqual(startup.send(None), 'PAUSE')
        finish(service.close())
        with self.assertRaises(RuntimeError): startup.send(None)
        startup.close()
        self.assertEqual(self.calls, [])

    def test_concurrent_close_waits_for_same_retirement(self):
        service = self.Service()
        visits = []
        async def cleanup():
            visits.append('begin')
            await self.Pause()
            visits.append('end')
        service.runner = types.SimpleNamespace(cleanup=cleanup)
        first = service.close()
        self.assertEqual(first.send(None), 'PAUSE')
        second = service.close()
        waiting = second.send(None)
        self.assertEqual(waiting[0], 'WAIT_TASK')
        with self.assertRaises(StopIteration): first.send(None)
        with self.assertRaises(StopIteration): second.send(None)
        self.assertEqual(visits, ['begin', 'end'])

    def test_startup_and_cleanup_errors_both_preserved(self):
        service = self.Service()
        self.site_error = RuntimeError('startup failed')
        self.runner_error = RuntimeError('cleanup failed')
        with self.assertRaises(BaseExceptionGroup) as caught: finish(service.start(0))
        self.assertEqual(caught.exception.exceptions, (self.site_error, self.runner_error))

    def test_close_waits_for_inflight_site_before_cleanup(self):
        service = self.Service()
        self.site_pause = True
        startup = service.start(0)
        self.assertEqual(startup.send(None), 'PAUSE')
        stopping = service.close()
        waiting = stopping.send(None)
        self.assertEqual(waiting[0], 'WAIT_TASK')
        self.assertIsNotNone(service.runner)
        # Site completes despite cancellation; startup must not publish success.
        waiting_start = startup.send(None)
        self.assertEqual(waiting_start[0], 'WAIT_TASK')
        with self.assertRaises(StopIteration): stopping.send(None)
        with self.assertRaises(RuntimeError): startup.send(None)
        self.assertIsNone(service.runner)
        self.assertTrue(service.task.done())

    def test_serve_keeps_combined_start_and_cleanup_errors(self):
        first, second = RuntimeError('start'), RuntimeError('cleanup')
        class Failed(self.Service):
            async def start(self, port): raise BaseExceptionGroup('both', [first, second])
            async def close(self): raise second
        self.namespace['OwnedWorkerService'] = lambda **kw: Failed()
        with self.assertRaises(BaseExceptionGroup) as caught: finish(self.namespace['serve'](0))
        self.assertEqual(caught.exception.exceptions, (first, second))


if __name__ == '__main__': unittest.main(verbosity=2)
