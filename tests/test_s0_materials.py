import copy,hashlib,pytest
from s0_smoke.materials import materials,validate_config
from s0_smoke.policy import validate_plan
from test_s0_policy import plan,H
# no native calls: test-only ephemeral cryptographic objects, never production keys.
def test_role_keys_context_and_config():
 m=materials(plan(),H,'b'*64)
 assert set(m)=={'LS5','PC4'}
 for role,files in m.items():
  c=validate_config(files['config.json'],H,'b'*64)
  assert c['role']==role
  assert files['tls-cert.pem']!=files['peer-cert.pem']
  assert b'PRIVATE KEY' in files['tls-key.pem']
 assert m['LS5']['tls-key.pem']!=m['PC4']['tls-key.pem']
def test_wrong_config_context():
 m=materials(plan(),H,'b'*64)
 for badhead,pin in [('c'*40,'b'*64),(H,'c'*64)]:
  with pytest.raises(ValueError):validate_config(m['LS5']['config.json'],badhead,pin)
def test_extra_configuration_rejected():
 import json
 c=json.loads(materials(plan(),H,'b'*64)['PC4']['config.json']);c['POSTGRES_DSN']='forbidden'
 with pytest.raises(ValueError):validate_config(json.dumps(c),H,'b'*64)
