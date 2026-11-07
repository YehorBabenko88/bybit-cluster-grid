"""Fixed synthetic bytes: structural/local consistency only, not authorization."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def c3(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def fixture():
    root = (HERE/'fixtures/manifest.canonical.json').read_bytes()
    objects = {}
    for name in ('data-schema', 'rows', 'segment-index', 'coverage', 'dependencies'):
        raw = (HERE/('fixtures/'+name+'.canonical.json')).read_bytes()
        objects[sha(raw)] = raw
    return root, objects


class FixtureCodecTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('query_fixture_codec', HERE.parents[1]/'grid/gateway_query.py')
        self.m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = self.m
        spec.loader.exec_module(self.m)

    def test_exact_fixture_explicit_gap_is_not_provider_coverage(self):
        result = self.m.decode_synthetic_fixture(*fixture())
        self.assertEqual(result['classification'], 'SYNTHETIC_FIXTURE_LOCALLY_CHECKED_ONLY')
        self.assertEqual(result['provider_coverage'], 'UNKNOWN')
        self.assertEqual(result['provider_gaps'], 'UNKNOWN')
        self.assertEqual(result['publication'], 'UNPROVEN')
        self.assertEqual([r[0] for r in result['rows']], ['0', '120000'])
        self.assertEqual([c['disposition'] for c in result['cells']], ['PRESENT', 'GAP', 'PRESENT'])
        self.assertFalse(result['execution_authority'])

    def test_missing_object_rejected_not_empty_history(self):
        root, objects = fixture(); objects.pop(next(iter(objects)))
        with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(root, objects)

    def test_bytes_hash_mismatch_rejected(self):
        root, objects = fixture(); key = next(iter(objects)); objects[key] += b'\n'
        with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(root, objects)

    def test_extra_object_not_silently_traversed(self):
        root, objects = fixture(); objects[sha(b'{}')] = b'{}'
        with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(root, objects)

    def test_claim_result_is_detached(self):
        result = self.m.decode_synthetic_fixture(*fixture()); result['rows'][0][1] = '999'
        self.assertEqual(self.m.decode_synthetic_fixture(*fixture())['rows'][0][1], '100')

    def test_oversized_manifest_refuses_before_any_hash(self):
        _, objects = fixture()
        with patch.object(self.m.hashlib, 'sha256', wraps=hashlib.sha256) as hashing:
            with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(b' '*16385,objects)
            self.assertEqual(hashing.call_count,0)

    def test_oversized_object_refuses_before_any_hash(self):
        root, objects = fixture();objects[next(iter(objects))]=b'x'*524289
        with patch.object(self.m.hashlib, 'sha256', wraps=hashlib.sha256) as hashing:
            with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(root,objects)
            self.assertEqual(hashing.call_count,0)

    def test_aggregate_oversize_refuses_before_any_hash(self):
        root, objects = fixture();objects={key:b'x'*220000 for key in objects}
        with patch.object(self.m.hashlib, 'sha256', wraps=hashlib.sha256) as hashing:
            with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(root,objects)
            self.assertEqual(hashing.call_count,0)

    def test_rehashed_semantic_mismatches_rejected(self):
        # Rebuild the entire dependency DAG so stale digests cannot mask joins.
        for change in ('row_duplicate', 'row_outside', 'ohlc', 'row_exponent',
                       'gap_has_row', 'coverage_hole', 'unknown_recoverability',
                       'count', 'lineage', 'schema', 'wrong_dependency'):
            with self.subTest(change=change):
                values = {n:json.loads((HERE/('fixtures/'+n+'.canonical.json')).read_bytes())
                          for n in ('manifest','rows','segment-index','coverage','dependencies')}
                r, idx, cov, dep, root = [values[n] for n in ('rows','segment-index','coverage','dependencies','manifest')]
                if change == 'row_duplicate': r['rows'][1][0] = '0'
                if change == 'row_outside': r['rows'][1][0] = '180000'
                if change == 'ohlc': r['rows'][0][1] = '999'
                if change == 'row_exponent': r['rows'][0][1] = '1e2'
                if change == 'gap_has_row': cov['cells'][0]['disposition']='GAP';cov['cells'][0]['reason']='FIXTURE_OMISSION';cov['cells'][0]['recoverability']='UNKNOWN'
                if change == 'coverage_hole': cov['cells'].pop(1)
                if change == 'unknown_recoverability': cov['cells'][1]['recoverability']='RECOVERED'
                if change == 'lineage': r['lineage_sha256']='e'*64
                if change == 'schema': r['data_schema_sha256']='e'*64
                rows_raw=c3(r); idx['segments'][0].update(sha256=sha(rows_raw),bytes=str(len(rows_raw)))
                if change == 'count': idx['segments'][0]['row_count']='3'
                index_raw=c3(idx); cov['segments_root_sha256']=sha(index_raw); coverage_raw=c3(cov)
                data_raw=(HERE/'fixtures/data-schema.canonical.json').read_bytes()
                dep['objects']=[{'role':role,'sha256':sha(raw),'bytes':str(len(raw))}
                                for role,raw in [('data_schema',data_raw),('rows',rows_raw),('segment_index',index_raw),('coverage',coverage_raw)]]
                if change == 'wrong_dependency': dep['objects'][0]['bytes']='1'
                dep_raw=c3(dep)
                root.update(segments_root_sha256=sha(index_raw),coverage_root_sha256=sha(coverage_raw),dependencies_root_sha256=sha(dep_raw))
                objects={sha(raw):raw for raw in (data_raw,rows_raw,index_raw,coverage_raw,dep_raw)}
                with self.assertRaises(self.m.QueryFormatError): self.m.decode_synthetic_fixture(c3(root),objects)

if __name__ == '__main__': unittest.main()
