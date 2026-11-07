"""Structural/runtime policy DATA tests; no native issuer or admission."""
import copy,json,unittest
from pathlib import Path
import jsonschema
from grid.authority_runtime_v1 import canonical
from grid.authority_assignment_v1 import parse_runtime_policy
ROOT=Path(__file__).resolve().parents[3]
POLICY_SCHEMA='runtime-actor-policy-review2.schema.json'
def policy():
    uid=lambda n:'00000000-0000-4000-8000-'+str(n).zfill(12)
    return dict(schema='unified.authority.runtime-actor-policy.v1-review2',state='ACTIVE',actor_node_id=uid(1),actor_session_id=uid(2),cluster_id=uid(3),enrollment_id=uid(4),identity_policy_id=uid(5),policy_id=uid(6),principal_id=uid(7),revision='1',job_ids=['job-1'],namespace='unified/'+uid(3),operations=['READ_ASSIGNMENT'],partition=dict(dataset_id=uid(8),source_id='fixture',partition_id='p1'))
class RuntimePolicyDataTests(unittest.TestCase):
    def test_schema_control_and13_terminal_newline_negatives(self):
        schema=json.loads((ROOT/'docs/coordination/assignment-v1'/POLICY_SCHEMA).read_bytes());validator=jsonschema.Draft202012Validator(schema);validator.check_schema(schema)
        value=policy();self.assertTrue(validator.is_valid(value))
        paths=[(key,) for key in ('actor_node_id','actor_session_id','cluster_id','enrollment_id','identity_policy_id','policy_id','principal_id','revision','namespace')]+[('partition',key) for key in ('dataset_id','source_id','partition_id')]+[('job_ids',0)]
        for path in paths:
            changed=copy.deepcopy(value);target=changed
            for key in path[:-1]:target=target[key]
            target[path[-1]]+=chr(10)
            with self.subTest(path=path):self.assertFalse(validator.is_valid(changed))
    def test_runtime_fullmatch_bounds_namespace_and_operation_semantics(self):
        value=policy();self.assertEqual(parse_runtime_policy(canonical(value)),value)
        mutations=[dict(value,revision='9223372036854775808'),dict(value,namespace='unified/00000000-0000-4000-8000-000000000099'),dict(value,operations=['WRITE_RUNTIME_POLICY']),dict(value,job_ids=['b','a']),dict(value,operations=['REVOKE','ASSIGN'])]
        for changed in mutations:
            with self.assertRaises(ValueError):parse_runtime_policy(canonical(changed))
        for field in ('actor_node_id','principal_id','revision','namespace'):
            changed=copy.deepcopy(value);changed[field]+=chr(10)
            raw=json.dumps(changed,sort_keys=True,separators=(',',':')).encode('ascii')
            with self.assertRaises(ValueError):parse_runtime_policy(raw)
    def test_schema_positive_u63_limit_and_no_implicit_policy_write(self):
        schema=json.loads((ROOT/'docs/coordination/assignment-v1'/POLICY_SCHEMA).read_bytes());v=jsonschema.Draft202012Validator(schema)
        self.assertTrue(v.is_valid(dict(policy(),revision='9223372036854775807')))
        for changed in (dict(policy(),revision='9223372036854775808'),dict(policy(),operations=['WRITE_RUNTIME_POLICY'])):self.assertFalse(v.is_valid(changed))
if __name__=='__main__':unittest.main()
