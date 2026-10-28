import copy
import unittest
from tools.s0_preparation_receipt import TOKEN_SOURCES, validate_token, validate_token_record
HEAD='a'*40

def fact():
    return dict(scope='HOSTED_FIXTURE_NOT_PHYSICAL',component='TOKEN_OBSERVER',head=HEAD,status='TEST_PASS',pure_cases=True,parent_admin_rejected=True,standard_primary_accepted=True,sid_matches=True,wrong_sid_rejected=True,medium=True,elevated=False,group_count=12,privilege_count=3,enabled_privilege_count=1,physical_acceptance=False)

class TokenPreparationReceiptTests(unittest.TestCase):
    def test_closed_observation_and_context(self):
        raw=fact(); self.assertIs(validate_token(raw,HEAD),raw)
        context=dict(head=HEAD,run_id='123',attempt='2'); sources={n:'b'*64 for n in TOKEN_SOURCES}
        full=dict(raw,run_id='123',attempt='2',source_sha256=sources,binary_sha256={'S0Launcher.dll':'c'*64,'TokenObserverFixture.exe':'d'*64})
        self.assertIs(validate_token_record(full,context,sources,'c'*64),full)
        for key,bad in [('run_id','124'),('attempt','3'),('source_sha256',{}),('binary_sha256',{'S0Launcher.dll':'c'*64})]:
            value=copy.deepcopy(full);value[key]=bad
            with self.assertRaises(ValueError):validate_token_record(value,context,sources,'c'*64)
        with self.assertRaises(ValueError):validate_token_record(full,context,sources,'e'*64)
        for changed in ({**sources,TOKEN_SOURCES[0]:'e'*64},{**sources,'unknown.cs':'b'*64}):
            value=copy.deepcopy(full);value['source_sha256']=changed
            with self.assertRaises(ValueError):validate_token_record(value,context,sources,'c'*64)
        for bad in (True,'01','0','1.0'):
            with self.assertRaises(ValueError):validate_token_record(full,{**context,'attempt':bad},sources,'c'*64)

    def test_rejects_fake_success_unknown_and_wrong_types(self):
        for key,bad in [('head','b'*40),('component','OTHER'),('status','PASS'),('pure_cases',1),('parent_admin_rejected',False),('standard_primary_accepted',False),('sid_matches',False),('wrong_sid_rejected',False),('medium',False),('elevated',0),('physical_acceptance',True),('group_count',True),('group_count',0),('group_count',4097),('privilege_count',1.0),('privilege_count',-1),('enabled_privilege_count',2),('enabled_privilege_count',True),('extra',0)]:
            value=fact();value[key]=bad
            with self.assertRaises(ValueError):validate_token(value,HEAD)
        value=fact();del value['pure_cases']
        with self.assertRaises(ValueError):validate_token(value,HEAD)
        value=fact();value.update(privilege_count=0,enabled_privilege_count=1)
        with self.assertRaises(ValueError):validate_token(value,HEAD)
