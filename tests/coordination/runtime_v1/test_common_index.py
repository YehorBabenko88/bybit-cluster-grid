import copy,hashlib,json,unittest
from pathlib import Path
import jsonschema
from grid.authority_runtime_v1 import canonical
ROOT=Path(__file__).resolve().parents[3]/'docs/coordination/runtime-v1'
class CommonIndexProposalTests(unittest.TestCase):
 def test_exact_hashes_and_closed_rows(self):
  schema=json.loads((ROOT/'common-index-review1.schema.json').read_bytes());vector=json.loads((ROOT/'common-index-review1.vectors.json').read_bytes());validator=jsonschema.Draft202012Validator(schema)
  pre=json.loads(vector['common_key_preimage_ascii']);validator.validate(pre)
  self.assertEqual(canonical(pre).decode(),vector['common_key_preimage_ascii'])
  self.assertEqual(hashlib.sha256(canonical(pre)).hexdigest(),vector['common_key_sha256'])
  self.assertNotEqual(vector['common_key_sha256'],vector['frozen_mux_key_sha256'])
  a=vector['request_binding'];b=vector['key_binding'];validator.validate(a);validator.validate(b)
  self.assertEqual({k:v for k,v in a.items() if k!='schema'},{k:v for k,v in b.items() if k!='schema'})
  for field,value in [('native_modify_index','1'),('kv_path','untrusted/path'),('generation','new'),('domain','SQLITE'),('request_id',True),('receipt_ref','UPPER'),('profile_schema_sha256','F'*64)]:
   bad=dict(a);bad[field]=value
   with self.subTest(field=field):self.assertTrue(list(validator.iter_errors(bad)))
if __name__=='__main__':unittest.main()
