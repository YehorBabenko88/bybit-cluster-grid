"""Pure local preparation tests; no actual disclosure/store proof."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


class PreparationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / 'grid' / 'gateway_query.py'
        spec = importlib.util.spec_from_file_location('gateway_query_under_test', path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def request(self):
        m = self.module
        return {
            'schema': m.REQUEST_SCHEMA,
            'request_id': '00000000-0000-4000-8000-000000000001',
            'dataset_id': '00000000-0000-4000-8000-000000000002',
            'dataset_revision': '2',
            'source_class': 'SYNTHETIC',
            'instrument_id': {'exchange': 'bybit', 'category': 'linear', 'symbol': 'BTCUSDT', 'instrument_version': '1'},
            'interval_ms': '60000',
            'data_schema_sha256': m.DATA_SCHEMA_SHA256,
            'query_profile_sha256': m.QUERY_PROFILE_SHA256,
            'range': {'start_ms': '0', 'end_ms': '120000'},
            'event_cut_ms': '120000',
            'knowledge_cut': {'manifest_sha256': 'a' * 64, 'manifest_revision': '1'},
            'consumer_context': {'consumer_id': '00000000-0000-4000-8000-000000000003', 'view_id': '00000000-0000-4000-8000-000000000004', 'authorization_contract_sha256': 'b' * 64},
        }

    def prepare(self, value=None):
        return self.module.prepare_query(canonical(self.request() if value is None else value))

    def test_valid_request_is_claim_and_blocked_not_empty_success(self):
        prepared = self.prepare()
        self.assertEqual(prepared.canonical_bytes, canonical(self.request()))
        self.assertEqual(prepared.request_sha256, hashlib.sha256(prepared.canonical_bytes).hexdigest())
        result = prepared.not_executed()
        self.assertEqual(result['status'], 'NOT_EXECUTED')
        self.assertEqual(result['reason_code'], 'DISCLOSURE_ADAPTER_NOT_ADMITTED')
        for field in ('rows', 'coverage', 'gaps', 'capabilities', 'resolved_manifest'):
            self.assertIsNone(result[field])
        self.assertFalse(result['native_authenticated'])

    def test_result_and_request_views_are_detached(self):
        p = self.prepare()
        p.as_dict()['consumer_context']['view_id'] = 'other'
        p.not_executed()['status'] = 'COMMITTED'
        self.assertEqual(p.as_dict(), self.request())
        self.assertEqual(p.not_executed()['status'], 'NOT_EXECUTED')
        with self.assertRaises((AttributeError, TypeError)):
            p.canonical_bytes = b'{}'

    def test_preparation_and_denial_have_zero_io(self):
        raw = canonical(self.request())
        with patch('builtins.open', side_effect=AssertionError('file IO forbidden')), patch('socket.socket', side_effect=AssertionError('socket IO forbidden')):
            p = self.module.prepare_query(raw)
            self.assertIsNone(p.not_executed()['rows'])

    def test_maximum_1440_rows_accepted_without_execution(self):
        v = self.request(); v['range']['end_ms'] = str(1440 * 60000); v['event_cut_ms'] = v['range']['end_ms']
        self.assertEqual(self.prepare(v).not_executed()['status'], 'NOT_EXECUTED')

    def test_old_retained_manifest_is_claim_not_replaced_with_latest(self):
        p = self.prepare()
        self.assertEqual(p.as_dict()['knowledge_cut']['manifest_revision'], '1')
        self.assertIsNone(p.not_executed()['resolved_manifest'])

    def test_dataset_and_manifest_revision_are_not_aliases(self):
        p = self.prepare()
        self.assertEqual(p.as_dict()['dataset_revision'], '2')
        self.assertEqual(p.as_dict()['knowledge_cut']['manifest_revision'], '1')

    def test_forged_prepared_bytes_revalidated_before_denial(self):
        with self.assertRaises(self.module.QueryFormatError):
            self.module.PreparedQuery(b'{}').not_executed()

    def test_profile_and_schema_are_exact_canonical_images(self):
        for raw, sha in ((self.module.data_schema_bytes(), self.module.DATA_SCHEMA_SHA256), (self.module.query_profile_bytes(), self.module.QUERY_PROFILE_SHA256)):
            self.assertEqual(canonical(json.loads(raw)), raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)


MUTATIONS = [
    ('schema', ('schema',), 'unknown'), ('source_class', ('source_class',), 'ACTUAL'),
    ('spot', ('instrument_id', 'category'), 'spot'), ('symbol', ('instrument_id', 'symbol'), 'ETHUSDT'),
    ('case', ('instrument_id', 'symbol'), 'btcusdt'), ('exchange', ('instrument_id', 'exchange'), 'other'),
    ('version_zero', ('instrument_id', 'instrument_version'), '0'),
    ('version_overflow', ('instrument_id', 'instrument_version'), '9223372036854775808'),
    ('version_number', ('instrument_id', 'instrument_version'), 1),
    ('profile', ('query_profile_sha256',), 'c' * 64), ('data_schema', ('data_schema_sha256',), 'c' * 64),
    ('dataset_uuid', ('dataset_id',), 'BTCUSDT'), ('request_uuid', ('request_id',), '00000000-0000-1000-8000-000000000001'),
    ('dataset_revision_zero', ('dataset_revision',), '0'),
    ('dataset_revision_overflow', ('dataset_revision',), '9223372036854775808'),
    ('consumer_label', ('consumer_context', 'consumer_id'), 'synthetic-research'),
    ('view_label', ('consumer_context', 'view_id'), 'fixture-view'),
    ('interval', ('interval_ms',), '300000'), ('empty', ('range', 'end_ms'), '0'),
    ('negative', ('range', 'start_ms'), '-1'), ('unaligned', ('range', 'start_ms'), '1'),
    ('range_bool', ('range', 'start_ms'), False), ('too_many', ('range', 'end_ms'), '86460000'),
    ('event_before_final_range', ('event_cut_ms',), '119999'),
    ('time_overflow', ('event_cut_ms',), '253402300800000'), ('leading_zero', ('event_cut_ms',), '0120000'),
    ('knowledge_null', ('knowledge_cut',), None), ('manifest_hash', ('knowledge_cut', 'manifest_sha256'), 'A' * 64),
    ('manifest_revision_zero', ('knowledge_cut', 'manifest_revision'), '0'),
    ('manifest_revision_float', ('knowledge_cut', 'manifest_revision'), 1.0),
    ('manifest_revision_overflow', ('knowledge_cut', 'manifest_revision'), '9223372036854775808'),
    ('consumer_null', ('consumer_context',), None), ('consumer_empty', ('consumer_context', 'consumer_id'), ''),
    ('view_newline', ('consumer_context', 'view_id'), 'fixture\n'),
    ('auth_hash', ('consumer_context', 'authorization_contract_sha256'), 'b' * 63),
]
for name, path, value in MUTATIONS:
    def test(self, path=path, value=value):
        v = self.request(); target = v
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value
        with self.assertRaises(self.module.QueryFormatError): self.prepare(v)
    setattr(PreparationTests, 'test_reject_' + name, test)

for name, transform in [
    ('duplicate', lambda raw: raw.replace(b'{', b'{"schema":"duplicate",', 1)),
    ('newline', lambda raw: raw + b'\n'), ('whitespace', lambda raw: b' ' + raw),
    ('non_ascii', lambda raw: raw.replace(b'BTCUSDT', b'BTCUSD\xc3\xa9')),
    ('escaped_ascii', lambda raw: raw.replace(b'BTCUSDT', b'BTCUSD\\u0054')),
    ('oversize', lambda raw: b' ' * 32769), ('deep', lambda raw: b'[' * 400 + b']' * 400),
    ('nan', lambda raw: raw.replace(b'"120000"', b'NaN', 1)),
    ('unknown_member', lambda raw: raw.replace(b'{', b'{"authorized":true,', 1)),
    ('missing_context', lambda raw: canonical({k:v for k,v in json.loads(raw).items() if k != 'consumer_context'})),
]:
    def test(self, transform=transform):
        with self.assertRaises(self.module.QueryFormatError): self.module.prepare_query(transform(canonical(self.request())))
    setattr(PreparationTests, 'test_reject_raw_' + name, test)

if __name__ == '__main__':
    unittest.main()
