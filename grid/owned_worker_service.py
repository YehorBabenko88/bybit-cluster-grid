"""Opt-in, source-bound loopback health for the existing DB-less Worker.

Importing coordinator reuses only identity/source checks; its ASGI app is never
served and its startup/shutdown handlers are never called.
"""
import argparse
import asyncio
import hashlib
import os
import pathlib
import secrets
import shutil
import time

from aiohttp import web

from . import coordinator as binding
from .config import settings
from .worker import Worker


class OwnedWorkerService:
    DATA_ONLY_PROFILE = 'grid.data-only-collector.v1'

    def __init__(self,*,data_first_admission=None,raw_capture_factory=None,launch_profile=None):
        if launch_profile is not None and (type(launch_profile) is not str or launch_profile != self.DATA_ONLY_PROFILE):
            raise ValueError('Owned worker launch profile unavailable')
        if raw_capture_factory is not None and not callable(raw_capture_factory):
            raise ValueError('Owned worker raw capture factory invalid')
        if launch_profile == self.DATA_ONLY_PROFILE and (raw_capture_factory is None or data_first_admission is not None):
            raise ValueError('Data-only worker requires raw capture without research admission')
        self.data_first_admission=data_first_admission
        self.raw_capture_factory=raw_capture_factory
        self.launch_profile=launch_profile
        self._started = False
        self._closed = False
        self._closing = False
        self._close_error = None
        self._close_task = None
        self._site_start_task = None
        self.identity = None
        self.worker = None
        self.task = None
        self.runner = None
        self.port = None

    def _owner_admitted_source_root(self,expected_commit):
        # No environment flag or duck-typed object grants foreign-owner scope.
        from .data_first_runtime import ProtectedDataFirstAdmission
        if type(self.data_first_admission) is not ProtectedDataFirstAdmission:return None
        root=self.data_first_admission.owner_admitted_grid_root(expected_commit)
        if str(root)!=str(binding._MODULE_SOURCE_ROOT):
            raise RuntimeError('Owned worker source binding unavailable')
        return root

    async def _bind_worker(self):
        if self._started or self._closed:
            raise RuntimeError('Owned worker already started')
        # Even failed startup is a consumed service lifetime, never an auto-retry.
        self._started = True
        identity = binding._owned_module_identity()
        if identity is None or settings.role != 'worker':
            raise RuntimeError('Owned worker profile unavailable')
        def verify():
            executable = pathlib.Path(os.environ.get('UNIFIED_GIT_EXECUTABLE', ''))
            digest = os.environ.get('UNIFIED_GIT_SHA256', '')
            if not executable.is_absolute() or not executable.is_file():
                return False
            resolved = shutil.which('git')
            if resolved is None or pathlib.Path(resolved).resolve() != executable.resolve():
                return False
            if executable.stat().st_size > 32 * 1024 * 1024:
                return False
            if not secrets.compare_digest(hashlib.sha256(executable.read_bytes()).hexdigest(), digest):
                return False
            owner_root=self._owner_admitted_source_root(identity[4])
            if owner_root is None:return binding._owned_source_is_clean(identity[4])
            return binding._owned_source_is_clean(identity[4],owner_admitted_root=owner_root)
        try:
            clean = await asyncio.wait_for(asyncio.to_thread(verify), 4)
        except Exception:
            clean = False
        if self._closed:
            raise RuntimeError('Owned worker closed during source verification')
        if clean is not True or binding._owned_module_identity() != identity:
            raise RuntimeError('Owned worker source binding unavailable')
        self.identity = identity
        kwargs = dict(data_first_admission=self.data_first_admission)
        if self.raw_capture_factory is not None:
            kwargs['raw_capture_factory'] = self.raw_capture_factory
        if self.launch_profile is not None:
            kwargs['launch_profile'] = self.launch_profile
        self.worker = Worker(**kwargs)

    async def start(self, port):
        if self.launch_profile == self.DATA_ONLY_PROFILE:
            raise RuntimeError('Data-only worker requires explicit offline input; listener start denied')
        await self._bind_worker()
        try:
            self.task = asyncio.create_task(self.worker.run(), name='owned-grid-worker')
            app = web.Application(client_max_size=1024)
            app.router.add_route('*', '/{path:.*}', self.health)
            self.runner = web.AppRunner(app, access_log=None, keepalive_timeout=1,
                                        max_line_size=2048, max_field_size=2048)
            await self.runner.setup()
            site = web.TCPSite(self.runner, '127.0.0.1', port)
            self._site_start_task = asyncio.create_task(site.start(), name='owned-grid-listener-start')
            await self._site_start_task
            if self._closed:
                raise RuntimeError('Owned worker closed during listener startup')
            self.port = site._server.sockets[0].getsockname()[1]
        except BaseException as startup_error:
            try:
                await self.close()
            except BaseException as cleanup_error:
                raise self._combined_error('Owned worker startup and shutdown failed',
                                           startup_error, cleanup_error) from None
            raise

    async def run_offline(self, frames, *, symbol, endpoint, observed_at_ms):
        """One finite actual Worker call; no listener, run(), provider or retry.

        Source custody still uses the existing binding. The profile restricts
        workload and is never a source, authority or network capability.
        """
        if self.launch_profile != self.DATA_ONLY_PROFILE:
            raise RuntimeError('Explicit data-only profile required')
        await self._bind_worker()
        try:
            self.task = asyncio.create_task(self.worker.receive_offline(
                frames, symbol=symbol, endpoint=endpoint, observed_at_ms=observed_at_ms),
                name='owned-grid-offline-worker')
            return await self.task
        finally:
            await self.close()

    async def health(self, request):
        headers = {'Cache-Control': 'no-store'}
        def error(status):
            return web.json_response({'error': 'MODULE_HEALTH_REJECTED'}, status=status, headers=headers)
        if request.method != 'GET':
            return error(405)
        if (request.raw_path != '/internal/v2/module/health'
                or request.headers.getall('Origin', [])
                or request.can_read_body
                or len(request.headers.getall('Host', [])) != 1
                or request.headers.get('Host') != '127.0.0.1:' + str(self.port)):
            return error(400)
        authorization = request.headers.getall('Authorization', [])
        if (len(authorization) != 1 or len(authorization[0]) > 256
                or not secrets.compare_digest(authorization[0].encode('utf-8'),
                                              ('Bearer ' + self.identity[3]).encode('ascii'))):
            return error(403)
        now = time.monotonic()
        heartbeat = self.worker.last_assignment_heartbeat
        ready = (binding._owned_module_identity() == self.identity
                 and self.task is not None and not self.task.done()
                 and heartbeat is not None
                 and 0 <= now - heartbeat < max(1.0, 3.0 * settings.heartbeat_seconds))
        return web.json_response(dict(module_id='grid', version=self.identity[1],
            release_id=self.identity[2], instance_token=self.identity[3], ready=ready),
            status=200 if ready else 503, headers=headers)

    async def close(self):
        # One retained retirement task: concurrent callers observe the same result.
        # Shielding keeps cancellation of a waiter from cancelling retirement.
        self._closed = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._shutdown(), name='owned-grid-worker-shutdown')
        return await asyncio.shield(self._close_task)

    @staticmethod
    def _combined_error(message, *errors):
        unique = []
        def collect(error):
            if isinstance(error, BaseExceptionGroup):
                for item in error.exceptions:
                    collect(item)
            elif not any(error is item for item in unique):
                unique.append(error)
        for error in errors:
            collect(error)
        return unique[0] if len(unique) == 1 else BaseExceptionGroup(message, unique)

    async def _shutdown(self):
        self._closing = True
        errors = []
        try:
            # A listener that finishes starting late must be joined before its
            # runner is cleaned. Never report closed then publish a new server.
            if self._site_start_task is not None:
                cancel_requested = not self._site_start_task.done()
                try:
                    if cancel_requested:
                        self._site_start_task.cancel()
                    outcomes = await asyncio.gather(self._site_start_task, return_exceptions=True)
                    for outcome in outcomes:
                        if isinstance(outcome, BaseException):
                            if cancel_requested and isinstance(outcome, asyncio.CancelledError):
                                continue
                            errors.append(outcome)
                except BaseException as error:
                    errors.append(error)
            if self.runner is not None:
                try:
                    await self.runner.cleanup()
                    self.runner = None
                except BaseException as error:
                    errors.append(error)
            if self.task is not None:
                cancel_requested = not self.task.done()
                try:
                    if cancel_requested:
                        self.task.cancel()
                    outcomes = await asyncio.gather(self.task, return_exceptions=True)
                    for outcome in outcomes:
                        if isinstance(outcome, BaseException):
                            if cancel_requested and isinstance(outcome, asyncio.CancelledError):
                                continue
                            errors.append(outcome)
                except BaseException as error:
                    errors.append(error)
        finally:
            self._closing = False
        if errors:
            self._close_error = self._combined_error('Owned worker shutdown failed', *errors)
            raise self._close_error


async def serve(port,*,data_first_admission=None):
    service = OwnedWorkerService(data_first_admission=data_first_admission)
    try:
        await service.start(port)
        await service.task
    except BaseException as primary_error:
        try:
            await service.close()
        except BaseException as cleanup_error:
            raise service._combined_error('Owned worker serving and shutdown failed',
                                          primary_error, cleanup_error) from None
        raise
    else:
        await service.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(argv)
    if not args.execute:
        return 0
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    asyncio.run(serve(args.port))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
