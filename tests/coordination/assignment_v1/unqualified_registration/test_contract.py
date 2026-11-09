"""Pure proposed registration DATA contract, no RPC or issued records."""
import copy,hashlib,importlib.util,json,unittest
from pathlib import Path
from grid.authority_runtime_v1 import canonical
from jsonschema import Draft202012Validator

ROOT=Path(__file__).absolute().parents[4]
HELPER=ROOT/'docs/coordination/assignment-v1/unqualified-worker-registration-v1/contract_data.py'

class RegistrationContractTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('registration_contract_data',HELPER)
        self.codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.codec)
        self.intent=dict(schema='unified.authority.unqualified-worker-registration-intent.v1-review1',
            operation='COMMISSION_UNQUALIFIED_WORKER',cluster_id='11111111-1111-4111-8111-111111111111',
            cluster_generation='22222222-2222-4222-8222-222222222222',realm_id='33333333-3333-4333-8333-333333333333',
            node_id='44444444-4444-4444-8444-444444444444',worker_inventory_incarnation_id='55555555-5555-4555-8555-555555555555',
            worker_module_sha256='a'*64,original_registration_request_id='66666666-6666-4666-8666-666666666666')
        self.raw=canonical(self.intent)
        self.record={k:v for k,v in self.intent.items() if k not in ('schema','operation')}
        self.record.update(schema='unified.authority.unqualified-worker-registration.v1-review1',
            original_registration_intent_sha256=hashlib.sha256(self.raw).hexdigest(),
            native_session_id='12345678-1234-1234-9234-123456789abc',registration_state='UNQUALIFIED',
            admitted_fields=[],resources_reserved=False,effect_permitted=False)
    def test_intent_is_closed_acyclic_and_exact_canonical(self):
        schema=json.loads((HELPER.parent/'intent.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(self.intent)
        self.assertEqual(self.codec.parse_intent(self.raw),self.intent)
        self.assertEqual(self.codec.intent_digest(self.raw),hashlib.sha256(self.raw).hexdigest())
        for extra in ('native_session_id','original_registration_intent_sha256','capacity'):
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.codec.parse_intent(canonical(dict(self.intent,**{extra:'not-allowed'})))
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(dict(self.intent,**{extra:'not-allowed'}))))
    def test_bad_encoding_duplicate_numeric_and_noncanonical_rejected(self):
        for raw in (self.raw+b'\n',b' '+self.raw,b'{"schema":"x","schema":"x"}',self.raw.replace(b'"COMMISSION_UNQUALIFIED_WORKER"',b'1'),self.raw.replace(b'"COMMISSION_UNQUALIFIED_WORKER"',b'true')):
            with self.subTest(raw=raw[:30]),self.assertRaises(ValueError):self.codec.parse_intent(raw)
    def test_record_exact_original_join_without_permission(self):
        self.assertEqual(self.codec.parse_record(canonical(self.record),original_intent_bytes=self.raw),self.record)
        for field,value in (('original_registration_request_id','77777777-7777-4777-8777-777777777777'),('original_registration_intent_sha256','b'*64),('worker_module_sha256','b'*64),('worker_inventory_incarnation_id','77777777-7777-4777-8777-777777777777')):
            with self.subTest(field=field),self.assertRaises(ValueError):self.codec.parse_record(canonical(dict(self.record,**{field:value})),original_intent_bytes=self.raw)
    def test_native_uuid_any_version_identity_uuid4_and_fullmatch(self):
        self.codec.parse_record(canonical(self.record),original_intent_bytes=self.raw)
        for sid in (self.record['native_session_id'].upper(),self.record['native_session_id']+'\n','not-session',True):
            with self.subTest(sid=sid),self.assertRaises(ValueError):self.codec.parse_record(canonical(dict(self.record,native_session_id=sid)),original_intent_bytes=self.raw)
        with self.assertRaises(ValueError):self.codec.parse_intent(canonical(dict(self.intent,node_id=self.record['native_session_id'])))
    def test_registration_cannot_upgrade_or_advertise_resources(self):
        schema=json.loads((HELPER.parent/'record.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(self.record)
        for field,value in (('registration_state','ACTIVE'),('admitted_fields',['cpu_millicores']),('resources_reserved',True),('effect_permitted',True),('resources_reserved','false'),('effect_permitted','false')):
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.codec.parse_record(canonical(dict(self.record,**{field:value})),original_intent_bytes=self.raw)
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(dict(self.record,**{field:value}))))
        with self.assertRaises(ValueError):self.codec.parse_record(canonical(dict(self.record,pid='123')),original_intent_bytes=self.raw)
    def test_only_allocated_registration_and_lock_keys(self):
        prefix='unified/'+self.intent['cluster_id']+'/runtime-v1/research-lab-v1/'+self.intent['realm_id']+'/workers/'+self.intent['node_id']+'/registration-v1'
        self.assertEqual(self.codec.registration_keys(self.raw),(prefix,prefix+'/lock'))
        for value in ('../foreign','node/foreign','',self.intent['node_id']+'\n'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.codec.registration_keys(canonical(dict(self.intent,node_id=value)))

if __name__=='__main__':unittest.main()
