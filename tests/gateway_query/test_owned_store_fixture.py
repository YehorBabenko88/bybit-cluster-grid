"""Actual disposable A4 store bytes, not authenticated query execution.

Explicit owner source root required; standalone local fixture test scope only.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('fixture_test_helpers',Path(__file__).with_name('test_fixture_codec.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
fixture,sha=helpers.fixture,helpers.sha

A4_HEAD = 'f9f2d04595cf2360dab78980996ae6c34c9e26fc'
A4_TREE = '7fa3c8ad67c4efece7e2a692f48fb63a9e40ffd3'


def verify_source(root, head=A4_HEAD, tree=A4_TREE):
    def git(*args):
        return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*args])
    assert git('rev-parse','HEAD').decode().strip() == head
    assert git('rev-parse','HEAD^{tree}').decode().strip() == tree
    assert not git('for-each-ref','--format=%(refname)','refs/replace').strip()
    assert not git('status','--porcelain','--untracked-files=all').strip()
    entries = [e.split(b'\t') for e in git('ls-tree','-rz','--full-tree','HEAD').split(b'\0') if e]
    oids = [meta.split()[2] for meta,_ in entries]
    stream = subprocess.check_output(['git','--no-replace-objects','-C',str(root),'cat-file','--batch'],input=b'\n'.join(oids)+b'\n')
    offset=0; result={}
    for (meta,path),oid in zip(entries,oids):
        line_end=stream.index(b'\n',offset); header=stream[offset:line_end].split()
        assert header[0]==oid and header[1]==b'blob'
        size=int(header[2]); raw=stream[line_end+1:line_end+1+size];offset=line_end+size+2
        name=path.decode();actual=(root/name).read_bytes();assert actual==raw,name
        result[name]=hashlib.sha256(raw).hexdigest()
    for path in root.rglob('*'):
        if '.git' in path.relative_to(root).parts:continue
        assert path.suffix.lower() not in ('.pyc','.pyo','.pyd','.so'),str(path)
        if path.is_file():assert path.relative_to(root).as_posix() in result,str(path)
    return result


@unittest.skipUnless(os.environ.get('GATEWAY_A4_SOURCE_ROOT'), 'explicit exact A4 source capsule required; actual store NOT_RUN')
class OwnedStoreFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['GATEWAY_A4_SOURCE_ROOT']).resolve()
        cls.before=verify_source(cls.root)
        sys.path.insert(0,str(cls.root))
        from unified_system.storage.object_store import ObjectStore
        from unified_system.storage.manifest import decode_manifest
        from unified_system.storage.contracts import StorageBlocked
        cls.store_type=ObjectStore;cls.manifest_decoder=staticmethod(decode_manifest)
        cls.storage_error=StorageBlocked

    @classmethod
    def tearDownClass(cls):
        assert verify_source(cls.root)==cls.before
        print('A4_PRIMARY_FILES_BEFORE_AFTER='+str(len(cls.before)))
        sys.path.remove(str(cls.root))

    def setUp(self):
        harness=helpers.FixtureCodecTests();harness.setUp();self.m=harness.m

    def test_actual_six_reads_reopen_and_codec_keep_gap_explicit(self):
        manifest,objects=fixture()
        with tempfile.TemporaryDirectory(prefix='agent3-synthetic-') as directory:
            path=Path(directory)/'owned'
            store=self.store_type.create(path,store_id='00000000-0000-4000-8000-000000000020')
            for raw in [manifest,*objects.values()]:store.put(raw)
            reopened=self.store_type.open(path,store_id='00000000-0000-4000-8000-000000000020')
            self.assertIsNot(store,reopened)
            root_bytes=reopened.read(sha(manifest),max_bytes=16384)
            claim=self.manifest_decoder(root_bytes)
            self.assertFalse(claim.publication_confirmed);self.assertFalse(claim.closure_verified)
            root=claim.as_dict()
            descriptor=root['data_schema_sha256'];index_key=root['segments_root_sha256']
            resolved={descriptor:reopened.read(descriptor,max_bytes=4096),
                      index_key:reopened.read(index_key,max_bytes=16384)}
            rows_key=json.loads(resolved[index_key])['segments'][0]['sha256']
            resolved[rows_key]=reopened.read(rows_key,max_bytes=524288)
            coverage_key=root['coverage_root_sha256'];deps_key=root['dependencies_root_sha256']
            resolved[coverage_key]=reopened.read(coverage_key,max_bytes=524288)
            resolved[deps_key]=reopened.read(deps_key,max_bytes=16384)
            self.assertEqual(sum(map(len,[root_bytes,*resolved.values()])),3433)
            result=self.m.decode_synthetic_fixture(root_bytes,resolved)
            self.assertEqual(result['cells'][1]['disposition'],'GAP')
            self.assertEqual(result['provider_coverage'],'UNKNOWN')
            # No query capability/current check, so this is NOT query execution.

    def test_actual_store_missing_object_refuses(self):
        with tempfile.TemporaryDirectory(prefix='agent3-synthetic-') as directory:
            store=self.store_type.create(Path(directory)/'owned',store_id='00000000-0000-4000-8000-000000000021')
            with self.assertRaisesRegex(self.storage_error,'OBJECT_UNAVAILABLE'):store.read('f'*64,max_bytes=16384)

    def test_actual_store_modified_owned_object_refuses_hash(self):
        with tempfile.TemporaryDirectory(prefix='agent3-synthetic-') as directory:
            path=Path(directory)/'owned'
            store=self.store_type.create(path,store_id='00000000-0000-4000-8000-000000000022')
            raw=b'local-synthetic-only';store.put(raw)
            (path/'objects'/sha(raw)).write_bytes(b'corrupt-owned-disposable-fixture')
            with self.assertRaisesRegex(self.storage_error,'OBJECT_CORRUPT'):store.read(sha(raw),max_bytes=16384)

if __name__ == '__main__':unittest.main()
