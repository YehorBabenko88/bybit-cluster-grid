"""Actual local Journal contract only; no native authority/session/permission."""
import base64,hashlib,importlib.util,sqlite3,tempfile,unittest,uuid
import json
from contextlib import closing
from unittest.mock import patch
from jsonschema import Draft202012Validator
from pathlib import Path
from unified_system.journal import Journal
from unified_system.contracts import ContractError
from grid.authority_runtime_v1 import canonical

ROOT=Path(__file__).absolute().parents[4]
FOLDER=ROOT/'docs/coordination/assignment-v1/unqualified-worker-registration-v1'

class CustodyContractTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('custody_contract_data',FOLDER/'custody_data.py')
        self.codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.codec)
        intent=dict(schema='unified.authority.unqualified-worker-registration-intent.v1-review1',operation='COMMISSION_UNQUALIFIED_WORKER',
            cluster_id=str(uuid.uuid4()),cluster_generation=str(uuid.uuid4()),realm_id=str(uuid.uuid4()),node_id=str(uuid.uuid4()),
            worker_inventory_incarnation_id=str(uuid.uuid4()),worker_module_sha256='a'*64,original_registration_request_id=str(uuid.uuid4()))
        self.raw=canonical(intent)
        self.original=dict(schema='unified.authority.unqualified-worker-registration-custody.v1-review1',
            original_registration_request_id=intent['original_registration_request_id'],original_registration_intent_sha256=hashlib.sha256(self.raw).hexdigest(),
            original_registration_intent_base64=base64.b64encode(self.raw).decode(),event='ORIGINAL_RETAINED',rpc_kind='NONE',rpc_attempt_id=None,
            native_session_id=None,endpoint_sha256=None,outcome='NOT_SENT',resources_reserved=False,effect_permitted=False)
    def test_real_journal_restart_retains_attempt_unknown_without_rpc(self):
        with tempfile.TemporaryDirectory(prefix='a2-registration-custody-') as tmp:
            path=Path(tmp)/'owned-registration.sqlite';journal=Journal(path);journal.initialize()
            journal.append('OBSERVING',self.original,expected_sequence=0)
            pending=dict(self.original,event='RPC_ATTEMPTED',rpc_kind='SESSION_CREATE',rpc_attempt_id=str(uuid.uuid4()),endpoint_sha256='b'*64,outcome='ATTEMPTED')
            journal.append('BLOCKED',pending,expected_sequence=1)
            self.codec.preflight_path(path)
            state=self.codec.replay(Journal(path).read(),original_intent_bytes=self.raw)
            self.assertEqual(state['local_transaction_report'],'NONE');self.assertEqual(state['unresolved_rpc_attempts'],[pending['rpc_attempt_id']])
            self.assertIsNone(state['native_session_id']);self.assertIs(state['effect_permitted'],False)
            with self.assertRaises(ContractError):journal.append('OBSERVING',self.original,expected_sequence=0)
            journal.append('BLOCKED',dict(pending,rpc_attempt_id=str(uuid.uuid4())),expected_sequence=2)
            with self.assertRaisesRegex(ValueError,'NO_AUTOMATIC_MUTATION_RETRY'):
                self.codec.replay(journal.read(),original_intent_bytes=self.raw)
            # Pure filesystem negative: sidecar directory-entry detection must
            # not trust exists(), which is false for a dangling link. No native
            # transport/session/issuer proof is mocked here.
            path.with_name(path.name+'-wal').write_bytes(b'untrusted-sidecar')
            with patch.object(Path,'exists',return_value=False),self.assertRaises(ValueError):
                self.codec.preflight_path(path)
    def test_closed_receipt_original_bounds_and_flags(self):
        schema=json.loads((FOLDER/'custody-receipt.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(self.original)
        self.assertEqual(self.codec.parse_receipt(canonical(self.original),original_intent_bytes=self.raw),self.original)
        for field,value in (('effect_permitted',True),('resources_reserved',True),('original_registration_intent_sha256','f'*64),('original_registration_intent_base64','!!!!'),('native_session_id',str(uuid.uuid4())),('foreign_domain','publication')):
            with self.subTest(field=field),self.assertRaises(ValueError):self.codec.parse_receipt(canonical(dict(self.original,**{field:value})),original_intent_bytes=self.raw)
    def test_real_foreign_corrupt_and_oversized_journal_refused(self):
        with tempfile.TemporaryDirectory(prefix='a2-registration-corrupt-') as tmp:
            path=Path(tmp)/'foreign.sqlite';journal=Journal(path);journal.initialize();journal.append('OBSERVING',{'schema':'foreign.domain'})
            with self.assertRaises(ValueError):self.codec.replay(journal.read(),original_intent_bytes=self.raw)
            with closing(sqlite3.connect(path)) as db:db.execute("UPDATE transitions SET digest='corrupt'");db.commit()
            with self.assertRaises(ContractError):journal.read()
            large=Path(tmp)/'oversized.sqlite';large.write_bytes(b'x'*(self.codec.MAX_DB_BYTES+1))
            with self.assertRaises(ValueError):self.codec.preflight_path(large)

if __name__=='__main__':unittest.main()
