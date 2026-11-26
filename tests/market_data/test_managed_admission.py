"""In-process admission fixtures only; no sockets, native scripts or services."""
from email.message import Message
from io import BytesIO
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from market_data import cli, history_api as gateway


ENV = dict(UNIFIED_MODULE_ID='market_data', UNIFIED_MODULE_VERSION='0.1.0',
           UNIFIED_RELEASE_ID='fixture-release', UNIFIED_INSTANCE_TOKEN='a' * 64)


class Admission:
    current = True

    def require_current(self):
        return self.current


class ManagedAdmissionTests(unittest.TestCase):
    def test_v1_health_and_capabilities_do_not_promote_database_to_source_readiness(self):
        with patch.object(gateway, 'query', return_value=[(180001, 'on')]):
            for route in ('/internal/v1/health', '/internal/v1/capabilities'):
                result = gateway.snapshot(route)
                self.assertEqual(result['api_version'], {'major': 1, 'minor': 0})
                self.assertEqual(result['producer'], 'market_data')
                self.assertIs(result['read_only'], True)
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertNotIn('instance_token', result)

    def test_denied_startup_never_binds_and_non_read_managed_mode_is_refused(self):
        admission = Admission()
        admission.current = False
        with patch.dict(os.environ, ENV, clear=True), patch.object(gateway, 'ThreadingHTTPServer') as factory:
            with self.assertRaises(RuntimeError):
                cli.main(['serve'], startup_admission=admission)
            factory.assert_not_called()
            with self.assertRaises(RuntimeError):
                cli.main(['capture', '--symbol', 'BTCUSDT', '--database', 'fixture',
                          '--source-revision', 'a' * 40], startup_admission=admission)

    def test_managed_startup_binds_only_loopback_after_callback(self):
        admission = Admission()
        bound = []

        class Server:
            def __init__(self, address, handler):
                bound.append(address)

            def serve_forever(self):
                self.running = True

            def server_close(self):
                self.closed = True

        with patch.dict(os.environ, ENV, clear=True), patch.object(gateway, 'ThreadingHTTPServer', Server):
            cli.main(['serve'], startup_admission=admission)
        self.assertEqual(bound, [('127.0.0.1', 18766)])

    def handler(self, admission, authorization):
        handler = gateway.Handler.__new__(gateway.Handler)
        handler.server = SimpleNamespace(module_identity=dict(module_id='market_data', version='0.1.0',
            release_id='fixture-release', instance_token='a' * 64), startup_admission=admission)
        handler.headers = Message()
        for value in authorization:
            handler.headers.add_header('Authorization', value)
        handler.path = '/health'
        handler.wfile = BytesIO()
        handler.send_response = lambda status: setattr(handler, 'status', status)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        return handler

    def test_health_requires_single_bearer_and_current_callback(self):
        for authorization in ([], ['wrong'], ['Bearer ' + 'a' * 64] * 2):
            handler = self.handler(Admission(), authorization)
            handler.do_GET()
            self.assertEqual(handler.status, 401)
            self.assertNotIn(b'instance_token', handler.wfile.getvalue())
        admission = Admission()
        handler = self.handler(admission, ['Bearer ' + 'a' * 64])
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertTrue(json.loads(handler.wfile.getvalue())['ready'])
        admission.current = False
        handler = self.handler(admission, ['Bearer ' + 'a' * 64])
        handler.do_GET()
        self.assertEqual(handler.status, 503)
        self.assertNotIn(b'instance_token', handler.wfile.getvalue())
