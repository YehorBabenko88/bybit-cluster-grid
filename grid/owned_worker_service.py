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
    def __init__(self):
        self.identity = None
        self.worker = None
        self.task = None
        self.runner = None
        self.port = None

    async def start(self, port):
        if self.task is not None or self.runner is not None:
            raise RuntimeError('Owned worker already started')
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
            return binding._owned_source_is_clean(identity[4])
        try:
            clean = await asyncio.wait_for(asyncio.to_thread(verify), 4)
        except Exception:
            clean = False
        if clean is not True or binding._owned_module_identity() != identity:
            raise RuntimeError('Owned worker source binding unavailable')
        self.identity = identity
        self.worker = Worker()
        self.task = asyncio.create_task(self.worker.run(), name='owned-grid-worker')
        app = web.Application(client_max_size=1024)
        app.router.add_route('*', '/{path:.*}', self.health)
        self.runner = web.AppRunner(app, access_log=None, keepalive_timeout=1,
                                    max_line_size=2048, max_field_size=2048)
        try:
            await self.runner.setup()
            site = web.TCPSite(self.runner, '127.0.0.1', port)
            await site.start()
            self.port = site._server.sockets[0].getsockname()[1]
        except BaseException:
            await self.close()
            raise

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
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def serve(port):
    service = OwnedWorkerService()
    try:
        await service.start(port)
        await service.task
    finally:
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
