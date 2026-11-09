"""Actual lifetime OS lock and fixed Journal; no native RPC/authority grants."""
import base64,json,os,subprocess,sys,tempfile,unittest,uuid
from pathlib import Path
from unified_system.journal import Journal
from grid import authority_assignment_v1 as native
from grid.authority_runtime_v1 import canonical

ROOT=Path(__file__).absolute().parents[4]
SUPPORT=Path(sys.modules['unified_system.journal'].__file__).absolute().parents[1]

class LocalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw=canonical(dict(schema='unified.authority.unqualified-worker-registration-intent.v1-review1',operation='COMMISSION_UNQUALIFIED_WORKER',
            cluster_id=str(uuid.uuid4()),cluster_generation=str(uuid.uuid4()),realm_id=str(uuid.uuid4()),node_id=str(uuid.uuid4()),
            worker_inventory_incarnation_id=str(uuid.uuid4()),worker_module_sha256='a'*64,original_registration_request_id=str(uuid.uuid4())))
    def child(self,path,mode):
        code='''import sys,base64,json
sys.path[:0]=sys.argv[1:3]
from unified_system.journal import Journal
from grid.authority_assignment_v1 import RootRegistrationCustody,RegistrationCustodyUnavailable
try:
 with RootRegistrationCustody(Journal(sys.argv[3]),original_intent_bytes=base64.b64decode(sys.argv[4],validate=True)) as owned:
  print(json.dumps(dict(status='ACQUIRED',effect_permitted=owned.read_state()['effect_permitted'])))
except RegistrationCustodyUnavailable as exc:
 print(json.dumps(dict(status='DENIED',reason=str(exc))))
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(SUPPORT),str(path),base64.b64encode(self.raw).decode()],
            capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertLessEqual(len(result.stdout)+len(result.stderr),4096)
        value=json.loads(result.stdout);self.assertEqual(value['status'],mode);return value
    def test_actual_other_process_denied_then_acquires_after_close(self):
        with tempfile.TemporaryDirectory(prefix='a2-root-custody-lock-') as tmp:
            path=Path(tmp)/'registration.sqlite'
            with native.RootRegistrationCustody(Journal(path),original_intent_bytes=self.raw) as owned:
                owned.retain_original();before=Journal(path).read()
                denied=self.child(path,'DENIED')
                self.assertEqual(denied['reason'],'EXCLUSIVE_ROOT_JOURNAL_OWNERSHIP_UNAVAILABLE')
                self.assertEqual(Journal(path).read(),before)
            self.assertIs(self.child(path,'ACQUIRED')['effect_permitted'],False)
    def test_actual_context_close_idempotence_and_original_error_preserved(self):
        with tempfile.TemporaryDirectory(prefix='a2-root-custody-close-') as tmp:
            path=Path(tmp)/'registration.sqlite';owned=native.RootRegistrationCustody(Journal(path),original_intent_bytes=self.raw)
            with self.assertRaisesRegex(RuntimeError,'ORIGINAL_ERROR'):
                with owned:
                    owned.retain_original();raise RuntimeError('ORIGINAL_ERROR')
            owned.close();owned.close()
            with self.assertRaises(native.RegistrationCustodyUnavailable):owned.read_state()
            with native.RootRegistrationCustody(Journal(path),original_intent_bytes=self.raw) as resumed:
                resumed.begin_rpc(rpc_kind='SESSION_CREATE',rpc_attempt_id=str(uuid.uuid4()),endpoint_sha256='b'*64)
            with native.RootRegistrationCustody(Journal(path),original_intent_bytes=self.raw) as resumed:
                self.assertEqual(len(resumed.read_state()['unresolved_rpc_attempts']),1)
                with self.assertRaises((ValueError,native.RegistrationCustodyUnavailable)):
                    resumed.begin_rpc(rpc_kind='SESSION_CREATE',rpc_attempt_id=str(uuid.uuid4()),endpoint_sha256='b'*64)
    def test_actual_foreign_file_mutated_path_and_sidecar_deny_before_append(self):
        with tempfile.TemporaryDirectory(prefix='a2-root-custody-foreign-') as tmp:
            foreign=Path(tmp)/'foreign.sqlite';Journal(foreign).initialize()
            with self.assertRaises(native.RegistrationCustodyUnavailable):native.RootRegistrationCustody(Journal(foreign),original_intent_bytes=self.raw)
            self.assertEqual(Journal(foreign).read(),[])
            path=Path(tmp)/'owned.sqlite';journal=Journal(path)
            with native.RootRegistrationCustody(journal,original_intent_bytes=self.raw) as owned:
                owned.retain_original();before=Journal(path).read()
                journal.path=foreign
                with self.assertRaises(native.RegistrationCustodyUnavailable):owned.read_state()
                journal.path=path
                path.with_name(path.name+'-journal').write_bytes(b'untrusted')
                with self.assertRaises(native.RegistrationCustodyUnavailable):
                    owned.begin_rpc(rpc_kind='SESSION_CREATE',rpc_attempt_id=str(uuid.uuid4()),endpoint_sha256='b'*64)
                self.assertEqual(len(before),1)

if __name__=='__main__':unittest.main()
