"""Future Data ownership refusals; no sockets, grants, stores or research validation."""
import importlib.util
import io
import unittest
from unittest.mock import patch


def data_api():
    # Canonical Data read API; no retired module fallback.
    from market_data import history_api
    return history_api


class ResearchOwnershipBoundaryTests(unittest.TestCase):
    def handler(self):
        api = data_api()
        handler = object.__new__(api.Handler)
        handler.path = '/internal/v1/research-handoffs/validate'
        handler._managed_request = lambda: True  # in-process route classification, no authority claim
        handler.headers = {'Content-Length': '2'}
        handler.rfile = io.BytesIO(b'{}')
        handler.wfile = io.BytesIO()
        handler.connection = type('InertConnection', (), {'settimeout': lambda self, value: None})()
        handler.statuses = []
        handler.send_error = lambda code: handler.statuses.append(code)
        handler.send_response = lambda code: handler.statuses.append(code)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        return api, handler

    def test_retired_research_route_refuses_before_body_read(self):
        api, handler = self.handler()
        class UnreadBody:
            def read(self, *args):
                raise AssertionError('RETIRED_ROUTE_MUST_NOT_READ_BODY')
        handler.rfile = UnreadBody()
        handler.do_POST()
        self.assertEqual(handler.statuses, [404])

    def test_retired_research_environment_is_not_consulted(self):
        api, handler = self.handler()
        accesses = []
        class InertEnvironment(dict):
            def get(self, key, default=None):
                if key == 'MARKET_DATA_TRUSTED_RESEARCH_SOURCES':
                    accesses.append(key)
                return super().get(key, default)
        with patch.object(api.os, 'environ', InertEnvironment()):
            handler.do_POST()
        self.assertEqual(accesses, [])
        self.assertEqual(handler.statuses, [404])

    def test_data_capabilities_do_not_own_research_import(self):
        capabilities = data_api().snapshot('/internal/v1/capabilities')['capabilities']
        self.assertNotIn('research_handoff_validation_v1_1', capabilities)

    def test_history_api_is_the_canonical_module(self):
        self.assertIsNotNone(importlib.util.find_spec('market_data.history_api'))

    def test_consumer_named_module_is_not_an_alias(self):
        self.assertIsNone(importlib.util.find_spec('market_data.terminan_gateway'))


if __name__ == '__main__':
    unittest.main()
